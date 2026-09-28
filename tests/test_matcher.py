from jobpilot.config import Criteria
from jobpilot.matcher import rule_score
from jobpilot.models import Job, find_apply_email, strip_html


def job(**kw):
    base = dict(source="t", external_id="1", title="Backend Developer Python", company="Acme",
                url="http://x", description="We use Python, Django and PostgreSQL.", location="Milano")
    base.update(kw)
    return Job(**base)


C = Criteria(keywords=["python", "backend", "django"], required_any=["python"], exclude=["php"],
             locations=["milano"], remote_ok=True, min_score=50)
SKILLS = ["python", "django", "postgresql", "docker"]


def test_good_match():
    m = rule_score(job(), C, SKILLS)
    assert m.passed and m.score > 70


def test_exclusion():
    m = rule_score(job(description="PHP and Python"), C, SKILLS)
    assert not m.passed and "php" in m.reasons[0]


def test_required_missing():
    assert not rule_score(job(title="Java dev", description="Java Spring"), C, SKILLS).passed


def test_location_and_remote():
    assert not rule_score(job(location="Berlin"), C, SKILLS).passed
    assert rule_score(job(location="Berlin", remote=True), C, SKILLS).passed


def test_word_boundaries():
    # "java" non deve corrispondere a "javascript"
    c = Criteria(required_any=["java"], min_score=0)
    assert not rule_score(job(title="JavaScript dev", description="javascript"), c, []).passed


def test_helpers():
    assert strip_html("<p>Ciao&nbsp;<b>mondo</b></p>") == "Ciao mondo"
    assert find_apply_email("Info: info@acme.it, invia il CV a careers@acme.it") == "careers@acme.it"
