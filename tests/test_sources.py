from jobpilot.sources import arbeitnow, greenhouse, lever, remotive, rss


def test_remotive_parse():
    jobs = remotive.parse({"jobs": [{"id": 5, "title": "Python Dev", "company_name": "A", "url": "u",
                                      "description": "<p>Send CV to jobs@a.com</p>", "tags": ["python"],
                                      "category": "Software", "candidate_required_location": "Europe"}]})
    assert jobs[0].remote and jobs[0].apply_email == "jobs@a.com" and jobs[0].external_id == "5"


def test_arbeitnow_parse():
    jobs = arbeitnow.parse({"data": [{"slug": "s1", "title": "T", "company_name": "C", "url": "u",
                                       "description": "d", "remote": False, "tags": [], "location": "Milano"}]})
    assert jobs[0].location == "Milano" and not jobs[0].remote


def test_greenhouse_parse():
    jobs = greenhouse.parse("acme", {"jobs": [{"id": 1, "title": "T", "absolute_url": "u",
                                                "location": {"name": "Remote - EU"}, "content": "&lt;p&gt;x&lt;/p&gt;"}]})
    assert jobs[0].remote and jobs[0].description == "x"


def test_lever_parse():
    jobs = lever.parse("acme", [{"id": "a", "text": "T", "hostedUrl": "u", "descriptionPlain": "d",
                                 "categories": {"location": "Milano"}, "workplaceType": "hybrid"}])
    assert jobs[0].location == "Milano" and not jobs[0].remote


def test_rss_parse():
    xml = """<rss><channel><item><title>Python Developer at Acme</title><link>http://j/1</link>
    <guid>1</guid><description>Remote role</description></item></channel></rss>"""
    jobs = rss.parse(xml, "test")
    assert jobs[0].company == "Acme" and jobs[0].title == "Python Developer" and jobs[0].remote
