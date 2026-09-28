"""Interfaccia a riga di comando di JobPilot."""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

from . import applier, pipeline
from .config import load_settings
from .db import STATUSES, Tracker
from .llm import LLM
from .mailer import Mailer


def _ctx(args):
    settings = load_settings(args.config)
    tracker = Tracker(settings.db_path)
    llm = LLM(settings.llm)
    mailer = Mailer(settings.email, dry_run=args.dry_run)
    return settings, tracker, llm, mailer


def _row_line(r) -> str:
    return f"{r['uid'][:8]}  {r['score']:5.1f}  {r['status']:<14} {r['title'][:45]:<45} @ {r['company'][:25]}"


def cmd_init(args):
    target = Path(args.config)
    if target.exists():
        print(f"{target} esiste già")
        return
    shutil.copy(Path(__file__).with_name("config.example.yaml"), target)
    print(f"Creato {target}: completa profilo, criteri e credenziali email.")


def cmd_scan(args):
    s, t, llm, _ = _ctx(args)
    matched = pipeline.scan(s, t, llm)
    print(f"{len(matched)} nuove offerte compatibili")
    for uid in matched:
        print(_row_line(t.get(uid)))


def cmd_list(args):
    _, t, _, _ = _ctx(args)
    for r in t.list(args.status):
        print(_row_line(r))


def cmd_show(args):
    _, t, _, _ = _ctx(args)
    r = t.get(args.uid)
    if not r:
        sys.exit("offerta non trovata")
    print(f"{r['title']} @ {r['company']}\n{r['url']}\nSede: {r['location']}  Remoto: {bool(r['remote'])}")
    print(f"Punteggio: {r['score']}  Stato: {r['status']}  Email candidatura: {r['apply_email'] or '-'}")
    for reason in json.loads(r["reasons"] or "[]"):
        print(f"  • {reason}")
    if r["cover_letter"]:
        print("\n--- Lettera ---\n" + r["cover_letter"])
    print("\n--- Cronologia ---")
    for e in t.events(r["uid"]):
        print(f"{e['created_at']}  {e['kind']:<10} {e['detail']}")
    if args.full:
        print("\n--- Descrizione ---\n" + (r["description"] or ""))


def cmd_approve(args):
    s, t, llm, _ = _ctx(args)
    for uid in args.uids:
        r = t.get(uid)
        if not r:
            print(f"{uid}: non trovata")
            continue
        if not r["cover_letter"]:
            t.update(r["uid"], cover_letter=applier.build_cover_letter(s, r, llm))
        t.set_status(r["uid"], "approved", "manuale")
        print(f"{r['uid'][:8]} approvata: {r['title']}")


def cmd_skip(args):
    _, t, _, _ = _ctx(args)
    for uid in args.uids:
        r = t.get(uid)
        if r:
            t.set_status(r["uid"], "discarded", "scartata manualmente")


def cmd_letter(args):
    s, t, llm, _ = _ctx(args)
    r = t.get(args.uid)
    if not r:
        sys.exit("offerta non trovata")
    if args.file:
        letter = Path(args.file).read_text(encoding="utf-8")
    else:
        letter = applier.build_cover_letter(s, r, llm)
    t.update(r["uid"], cover_letter=letter)
    print(letter)


def cmd_apply(args):
    s, t, llm, mailer = _ctx(args)
    if args.uid:
        r = t.get(args.uid)
        if not r:
            sys.exit("offerta non trovata")
        print(applier.apply(s, t, r["uid"], mailer, llm))
    else:
        for uid, status in pipeline.apply_approved(s, t, mailer, llm).items():
            print(f"{uid[:8]} → {status}")


def cmd_mail(args):
    s, t, llm, mailer = _ctx(args)
    for res in pipeline.check_mail(s, t, mailer, llm):
        print(f"{(res['uid'] or '-')[:8]:<8} {res['category']:<14} {res['subject'][:60]}"
              + ("  [bozza di risposta]" if res["draft"] else ""))


def cmd_replies(args):
    _, t, _, _ = _ctx(args)
    for e in t.emails(pending_only=True):
        print(f"=== {e['message_id']}\nDa: {e['sender']}\nOggetto: {e['subject']}\nCategoria: {e['category']}\n"
              f"Riassunto: {e['summary']}\n--- Bozza ---\n{e['draft_reply']}\n")


def cmd_send_reply(args):
    _, t, _, mailer = _ctx(args)
    e = next((e for e in t.emails(pending_only=True) if e["message_id"] == args.message_id), None)
    if not e:
        sys.exit("bozza non trovata")
    body = Path(args.file).read_text(encoding="utf-8") if args.file else e["draft_reply"]
    subj = e["subject"] if e["subject"].lower().startswith("re:") else f"Re: {e['subject']}"
    from email.utils import parseaddr
    mailer.send(parseaddr(e["sender"])[1], subj, body, in_reply_to=e["message_id"])
    t.mark_reply_sent(e["message_id"])
    t.log(e["job_uid"], "reply_sent", subj)
    print("risposta inviata")


def cmd_set_status(args):
    _, t, _, _ = _ctx(args)
    r = t.get(args.uid)
    if not r:
        sys.exit("offerta non trovata")
    t.set_status(r["uid"], args.status, "manuale")


def cmd_status(args):
    _, t, _, _ = _ctx(args)
    stats = t.stats()
    for st in STATUSES:
        if stats.get(st):
            print(f"{st:<15} {stats[st]}")
    active = t.active_applications()
    if active:
        print("\nCandidature in corso:")
        for r in active:
            print(_row_line(r))


def cmd_followups(args):
    s, t, _, mailer = _ctx(args)
    for uid in pipeline.followups(s, t, mailer, send=args.send):
        r = t.get(uid)
        print(f"{uid[:8]} follow-up {'inviato' if args.send else 'da inviare'}: {r['title']} @ {r['company']}")


def cmd_run(args):
    s, t, llm, mailer = _ctx(args)
    while True:
        summary = pipeline.run_cycle(s, t, mailer, llm)
        print(f"[ciclo] compatibili={len(summary['matched'])} auto-approvate={len(summary['auto_approved'])} "
              f"inviate={len(summary['applied'])} email={len(summary['emails'])} follow-up={len(summary['followups'])}")
        if args.once:
            break
        time.sleep(args.interval * 60)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jobpilot", description="Monitoraggio offerte e gestione candidature")
    ap.add_argument("-c", "--config", default="config.yaml")
    ap.add_argument("--dry-run", action="store_true", help="non invia email reali")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="crea config.yaml di esempio").set_defaults(fn=cmd_init)
    sub.add_parser("scan", help="cerca e valuta nuove offerte").set_defaults(fn=cmd_scan)
    p = sub.add_parser("list", help="elenca offerte (default: tutte tranne scartate)")
    p.add_argument("status", nargs="?", choices=STATUSES)
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show", help="dettagli di un'offerta")
    p.add_argument("uid"); p.add_argument("--full", action="store_true"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("approve", help="approva offerte per la candidatura")
    p.add_argument("uids", nargs="+"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("skip", help="scarta offerte")
    p.add_argument("uids", nargs="+"); p.set_defaults(fn=cmd_skip)
    p = sub.add_parser("letter", help="rigenera o imposta la lettera di presentazione")
    p.add_argument("uid"); p.add_argument("--file"); p.set_defaults(fn=cmd_letter)
    p = sub.add_parser("apply", help="invia le candidature approvate (o una specifica)")
    p.add_argument("uid", nargs="?"); p.set_defaults(fn=cmd_apply)
    sub.add_parser("mail", help="controlla la posta e aggiorna gli stati").set_defaults(fn=cmd_mail)
    sub.add_parser("replies", help="mostra le bozze di risposta").set_defaults(fn=cmd_replies)
    p = sub.add_parser("send-reply", help="invia una bozza di risposta")
    p.add_argument("message_id"); p.add_argument("--file", help="testo modificato"); p.set_defaults(fn=cmd_send_reply)
    p = sub.add_parser("set-status", help="aggiorna manualmente lo stato")
    p.add_argument("uid"); p.add_argument("status", choices=STATUSES); p.set_defaults(fn=cmd_set_status)
    sub.add_parser("status", help="riepilogo").set_defaults(fn=cmd_status)
    p = sub.add_parser("followups", help="solleciti per candidature senza risposta")
    p.add_argument("--send", action="store_true"); p.set_defaults(fn=cmd_followups)
    p = sub.add_parser("run", help="ciclo completo, ripetuto a intervalli")
    p.add_argument("--once", action="store_true"); p.add_argument("--interval", type=int, default=60, help="minuti")
    p.set_defaults(fn=cmd_run)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    args.fn(args)


if __name__ == "__main__":
    main()
