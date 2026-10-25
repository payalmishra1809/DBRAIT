"""Pure rules: grading, credits, attendance. Source: NSCBIHL result pages, 2024-25 CSE scheme, Oct 2026 circulars."""
import re

GRADE_POINTS = {"A+": 10, "A": 9, "B": 8, "C": 7, "D": 6, "E": 5, "F": 0}
NO_CREDIT = {"IL107", "SY114", "CI208", "ES215", "IKS306"}   # Mandatory Pass (MP), not in SGPA
FEE = 150  # Rs per subject per semester (condonation)

# (sem, code, name, L, T, P)
CURRICULUM = [
 (1,"CH101","Engineering Chemistry",3,0,2),(1,"MA102","Linear Algebra & Calculus",3,1,0),
 (1,"EE103","Basic Electrical & Electronics Engg",3,0,2),(1,"EG104","Engineering Graphics & Design",1,0,4),
 (1,"CP105","Computer Fundamentals & C Programming",3,0,4),(1,"DT106","Design Thinking",0,0,2),(1,"IL107","IDEA Lab",2,0,4),
 (2,"PH108","Engineering Physics",3,0,2),(2,"MA109","Matrices & Complex Variables",3,1,0),(2,"CS110","Python Programming",2,0,4),
 (2,"EN111","English for Technical Writing",2,0,2),(2,"WP112","Workshop Practices",0,0,4),(2,"UHV113","Universal Human Values",2,1,0),(2,"SY114","Sports and Yoga",0,0,2),
 (3,"CS201","Data Structures",3,0,4),(3,"CS202","Computer Organization & Architecture",3,0,0),(3,"CS203","Computer Graphics & Image Processing",3,0,2),
 (3,"CS204","IT Workshop (SciLab/MATLAB)",0,0,4),(3,"MA204","Probability & Statistics",2,1,0),(3,"DL205","Digital Logic Design",3,0,2),
 (3,"SM206","Survey of Music Technology",2,0,2),(3,"CI208","Constitution of India / IKT",2,0,0),
 (4,"CS209","Discrete Mathematics",3,0,0),(4,"CS210","Design & Analysis of Algorithms",3,0,4),(4,"CS211","Advanced Programming",2,0,4),
 (4,"MM212","Microprocessor & Microcontroller",2,0,2),(4,"HM213","Organizational Behavior Management",3,0,0),(4,"ES215","Environmental Sciences",2,0,0),
 (5,"CS301","Software Engineering",3,1,0),(5,"CS302","Introduction to Database Systems",3,0,4),(5,"CS303","Theory of Computation",3,1,0),
 (5,"CS304","Operating Systems",3,0,4),(5,"CL305","Cyber Law",3,0,0),(5,"IKS306","Indian Knowledge System",2,0,0),
 (6,"CS307","Computer Networks",3,0,4),(6,"CS308","Compiler Design",3,0,2),(6,"CS309","Machine Learning",3,0,4),
 (6,"CSE310","Elective-I",3,0,0),(6,"OE311","Open Elective-I",3,0,0),
 (7,"CS401","Network & Cyber Security",4,0,4),(7,"CSE402","Elective-II",3,0,0),(7,"OE403","Open Elective-II",3,0,0),
 (7,"PP404","Project Phase-I",0,0,12),(7,"CV405","Comprehensive Viva-Voce",0,0,4),
 (8,"CSE406","Elective-III",3,0,0),(8,"CSE407","Elective-IV",3,0,0),(8,"OE408","Open Elective-III",3,0,0),
 (8,"PP409","Project Phase-II",0,0,18),(8,"IN410","Internship",0,0,2),(8,"SM411","Seminar",0,0,4),
]

def components(code, L, T, P):
    """Result pages grade theory (T) and lab (P) separately. Theory credit = L+T, lab = P/2."""
    pre, num = re.match(r"([A-Z]+)(\d+)", code).groups()
    out = []
    if L + T > 0:
        cr = 0 if code in NO_CREDIT or code == "EG104" else L + T   # EG104 theory is MP; its 2 credits sit in the lab
        out.append({"code": f"{pre} T{num}", "kind": "Theory", "credits": cr})
    if P > 0:
        cr = 0 if code in NO_CREDIT else P / 2
        out.append({"code": f"{pre} P{num}", "kind": "Lab", "credits": cr})
    return out

def sgpa(rows):
    """rows: [(credits, grade)] -> SGPA; MP/blank rows and 0-credit rows are skipped."""
    pts = [(c, GRADE_POINTS[g]) for c, g in rows if g in GRADE_POINTS and c > 0]
    tot = sum(c for c, _ in pts)
    return round(sum(c * p for c, p in pts) / tot, 2) if tot else None

def attendance_status(attended, total, medical=False, activity=False):
    """Course-wise rule: >=75 eligible; 65-<75 condonable (medical + Rs150) or concession (activity, no fee); else defaulter."""
    if total <= 0:
        return {"pct": None, "status": "No classes yet", "fee": 0}
    pct = round(100 * attended / total, 2)
    if pct >= 75: s, fee = "Eligible", 0
    elif pct >= 65 and activity: s, fee = "Concession (activity)", 0
    elif pct >= 65 and medical: s, fee = "Condonable (medical)", FEE
    elif pct >= 65: s, fee = "Needs HoD approval", 0
    else: s, fee = "Defaulter", 0
    return {"pct": pct, "status": s, "fee": fee}

def classes_to_75(attended, total):
    """>0: classes you must attend in a row to reach 75%; <0: classes you can still miss."""
    if total <= 0: return 0
    if attended / total >= 0.75:
        k = 0
        while attended / (total + k + 1) >= 0.75: k += 1
        return -k
    k = 0
    while (attended + k) / (total + k) < 0.75: k += 1
    return k
