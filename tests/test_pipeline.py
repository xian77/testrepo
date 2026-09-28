from email.message import EmailMessage

from jobpilot import inbox, pipeline
from jobpilot.mailer import Mailer
from jobpilot.models import Job


class FakeMailer(Mailer):
    def __init__(self):
        super().__init__({"address": "anna@example.com"}, dry_run=True)
        self.sent = []

    def send(self, to, subject, body, attachments=(), in_reply_to=None):
        self.sent.append((to, subject, body, in_reply_to))
        return "<id@x>"


def jobs():
    return [
        Job("t", "1", "Backend Developer Python", "Acme", "http://a", "Python Django. Send CV to careers@acme.com",
            "Milano", apply_email="careers@acme.com"),
        Job("t", "2", "Python Engineer", "Globex", "http://g", "Python and Docker, remote", "Remote", remote=True),
        Job("t", "3", "PHP Developer", "Initech", "http://i", "PHP Python", "Milano"),
    ]


def test_full_flow(settings, tracker):
    mailer = FakeMailer()
    matched = pipeline.scan(settings, tracker, jobs=jobs())
    assert len(matched) == 2
    # rilanciare lo scan non duplica le offerte
    assert pipeline.scan(settings, tracker, jobs=jobs()) == []

    approved = pipeline.auto_approve(settings, tracker)
    assert approved
    result = pipeline.apply_approved(settings, tracker, mailer)
    acme = jobs()[0].uid
    assert result[acme] == "applied"
    assert mailer.sent[0][0] == "careers@acme.com" and "Anna Bianchi" in mailer.sent[0][2]
    globex = jobs()[1].uid
    if globex in result:
        assert result[globex] == "manual_pending"
        assert (settings.base_dir / "packets" / f"{globex}.md").exists()

    # risposta con invito a colloquio
    msg = inbox.Incoming("<m1@acme.com>", "Laura HR <laura@acme.com>", "La sua candidatura - Backend Developer Python",
                         "2026-01-01", "Buongiorno, vorremmo fissare un colloquio. Ci indichi la sua disponibilità.")
    res = inbox.process([msg], tracker, settings.profile, settings.email, mailer)
    assert res[0]["uid"] == acme and res[0]["category"] == "interview" and res[0]["draft"]
    assert tracker.get(acme)["status"] == "interview"
    assert "martedì o giovedì" in tracker.emails(pending_only=True)[0]["draft_reply"]
    # stessa email non viene rielaborata
    assert inbox.process([msg], tracker, settings.profile, settings.email, mailer) == []

    # un messaggio di conferma successivo non fa regredire lo stato
    ack = inbox.Incoming("<m2@acme.com>", "noreply@acme.com", "Grazie", "2026-01-02",
                         "Grazie per la candidatura, abbiamo ricevuto il suo CV.")
    inbox.process([ack], tracker, settings.profile, settings.email, mailer)
    assert tracker.get(acme)["status"] == "interview"

    rej = inbox.Incoming("<m3@acme.com>", "hr@acme.com", "Aggiornamento", "2026-01-03",
                         "Purtroppo abbiamo deciso di proseguire con altri candidati.")
    inbox.process([rej], tracker, settings.profile, settings.email, mailer)
    assert tracker.get(acme)["status"] == "rejected"


def test_irrelevant_email_ignored(settings, tracker):
    msg = inbox.Incoming("<n@x>", "news@shop.com", "Saldi!", "2026-01-01", "Sconti del 50%")
    assert inbox.process([msg], tracker, settings.profile, settings.email) == []


def test_parse_message():
    m = EmailMessage()
    m["From"] = "HR <hr@acme.com>"; m["Subject"] = "Colloquio"; m["Message-ID"] = "<x@y>"
    m["Date"] = "Mon, 01 Sep 2026 10:00:00 +0200"
    m.set_content("Testo")
    inc = inbox.parse_message(m.as_bytes())
    assert inc.domain == "acme.com" and inc.body == "Testo" and inc.message_id == "<x@y>"


def test_followup(settings, tracker):
    mailer = FakeMailer()
    pipeline.scan(settings, tracker, jobs=jobs()[:1])
    uid = jobs()[0].uid
    tracker.update(uid, applied_at="2020-01-01T00:00:00+00:00")
    tracker.set_status(uid, "applied")
    assert pipeline.followups(settings, tracker, mailer, send=True) == [uid]
    assert pipeline.followups(settings, tracker, mailer, send=True) == []  # una volta sola
    assert len(mailer.sent) == 1
