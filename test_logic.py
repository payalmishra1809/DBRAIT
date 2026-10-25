from logic import *
def test_components():
    assert [c["credits"] for c in components("CP105",3,0,4)] == [3, 2]
    assert [c["credits"] for c in components("EG104",1,0,4)] == [0, 2]
    assert all(c["credits"] == 0 for c in components("IL107",2,0,4))
def test_semester_credits_match_curriculum():
    want = {1:20, 2:20, 3:24, 4:18, 5:21}
    for s, w in want.items():
        got = sum(c["credits"] for r in CURRICULUM if r[0]==s for c in components(r[1],*r[3:]))
        assert got == w, (s, got)
def test_sgpa():
    assert sgpa([(3,"A"),(2,"B"),(2,"MP"),(0,"A+")]) == 8.6
    assert sgpa([(3,"F")]) == 0.0 and sgpa([]) is None
def test_attendance():
    assert attendance_status(75,100)["status"] == "Eligible"
    assert attendance_status(70,100,medical=True) == {"pct":70.0,"status":"Condonable (medical)","fee":150}
    assert attendance_status(70,100,activity=True)["fee"] == 0
    assert attendance_status(64,100)["status"] == "Defaulter"
    assert classes_to_75(60,100) == 60 and classes_to_75(90,100) == -20
