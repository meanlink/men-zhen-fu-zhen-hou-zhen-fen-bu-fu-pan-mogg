"""改善验收时段占用、撤回留档与并发规则的端到端验证。

运行：cd backend && python -m pytest tests/test_improvement_claims.py -q
"""
import os
import tempfile
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["REDIS_URL"] = "redis://localhost:6390/0"

from src.auth import hash_password  # noqa: E402
from src.database import SessionLocal, init_db  # noqa: E402
from src.main import app  # noqa: E402
from src.models import (  # noqa: E402
    DepartmentSlot, ImprovementSlotClaim, SampleStatus, User, UserRole, WaitSample,
)
from src.services.workflow import create_report, review_report  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def setup_data():
    init_db()
    db = SessionLocal()
    users = {}
    for username, display, role in [
        ("analyst", "分析专员", UserRole.ANALYST),
        ("reviewer", "科室复核员", UserRole.DEPARTMENT_REVIEWER),
        ("admin", "运营管理员", UserRole.OPERATIONS_ADMIN),
    ]:
        user = db.query(User).filter_by(username=username).first()
        if not user:
            user = User(username=username, display_name=display, role=role,
                        password_hash=hash_password("demo123"))
            db.add(user)
            db.flush()
        users[username] = user
    db.commit()
    db.close()
    yield


def _token(client, username):
    resp = client.post("/auth/login", json={"username": username, "password": "demo123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(client, username):
    return {"Authorization": f"Bearer {_token(client, username)}"}


def _slot(db, dept, day):
    slot = DepartmentSlot(department_name=dept, slot_date=date(2026, 11, day),
                          slot_label="随访加开窗", start_time=time(9), end_time=time(11),
                          threshold_minutes=30, capacity=12)
    db.add(slot)
    db.flush()
    base = datetime.combine(slot.slot_date, time(9))
    for i, wait in enumerate([20, 24, 28, 58] if day < 15 else [10, 12, 15, 20], start=1):
        appointment = base + timedelta(minutes=8 * (i - 1))
        checkin = appointment + timedelta(minutes=2)
        db.add(WaitSample(
            sample_code=f"{dept[:2]}-{day}-{i:02}-{datetime.utcnow().microsecond}",
            patient_alias=f"代号{i}", department_slot_id=slot.id,
            appointment_time=appointment, checkin_time=checkin,
            called_time=checkin + timedelta(minutes=wait),
            completed_time=checkin + timedelta(minutes=wait + 10),
            status=SampleStatus.COMPLETED, source_channel="电话预约", created_by=1,
        ))
    db.commit()
    return slot


def _reviewed_report(db, slot, title, analyst, reviewer):
    report = create_report(db, slot.id, title, analyst)
    return review_report(db, report, reviewer, "已逐条核对候诊记录与时段分布。")


def _make_improvement(client, db, dept, baseline_day, target):
    analyst = db.query(User).filter_by(username="analyst").first()
    reviewer = db.query(User).filter_by(username="reviewer").first()
    slot = _slot(db, dept, baseline_day)
    report = _reviewed_report(db, slot, f"{dept} 基线 {baseline_day}", analyst, reviewer)
    anomaly = (db.query(WaitSample)
               .filter_by(department_slot_id=slot.id)
               .order_by(WaitSample.id.desc()).first())
    resp = client.post("/improvements", headers=_auth(client, "analyst"), json={
        "baseline_report_id": report.id,
        "anomaly_sample_code": anomaly.sample_code,
        "target_p90": target,
        "action_plan": f"{dept} 改善措施：分流加号并加密巡诊。",
    })
    assert resp.status_code == 201, resp.text
    improvement = resp.json()
    resp = client.post(f"/improvements/{improvement['id']}/implement",
                       headers=_auth(client, "admin"),
                       json={"implemented_on": "2026-11-12",
                             "implementation_note": "已按方案调整排班与分诊。"})
    assert resp.status_code == 200, resp.text
    return improvement


def _comparison_slot(db, dept, day, waits):
    slot = DepartmentSlot(department_name=dept, slot_date=date(2026, 11, day),
                          slot_label="随访加开窗", start_time=time(9), end_time=time(11),
                          threshold_minutes=30, capacity=12)
    db.add(slot)
    db.flush()
    base = datetime.combine(slot.slot_date, time(9))
    for i, wait in enumerate(waits, start=1):
        appointment = base + timedelta(minutes=8 * (i - 1))
        checkin = appointment + timedelta(minutes=2)
        db.add(WaitSample(
            sample_code=f"{dept[:2]}-C{day}-{i:02}-{datetime.utcnow().microsecond}",
            patient_alias=f"复测代号{i}", department_slot_id=slot.id,
            appointment_time=appointment, checkin_time=checkin,
            called_time=checkin + timedelta(minutes=wait),
            completed_time=checkin + timedelta(minutes=wait + 10),
            status=SampleStatus.COMPLETED, source_channel="线上预约", created_by=1,
        ))
    db.commit()
    return slot


def test_redo_reports_each_usable_and_slot_freed_by_withdrawal(client):
    """规则 1+4：同时段重做的两份报告可分别成为两个事项的成效证据，
    但靠撤回释放时段串起来；撤回结论留档。"""
    db = SessionLocal()
    try:
        i1 = _make_improvement(client, db, "呼吸内科", 10, 35)
        i2 = _make_improvement(client, db, "呼吸内科", 11, 30)
        analyst = db.query(User).filter_by(username="analyst").first()
        reviewer = db.query(User).filter_by(username="reviewer").first()
        slot_s = _comparison_slot(db, "呼吸内科", 16, [10, 12, 15, 20])
        r1 = _reviewed_report(db, slot_s, "呼吸内科 复测 第一版", analyst, reviewer)
        r2 = _reviewed_report(db, slot_s, "呼吸内科 复测 重做版", analyst, reviewer)
        assert r1.id != r2.id and r1.department_slot_id == r2.department_slot_id

        # I1 用第一版报告验收，认领时段 S。
        resp = client.post(f"/improvements/{i1['id']}/evaluate", headers=_auth(client, "reviewer"),
                           json={"comparison_report_id": r1.id, "evaluation_note": "P90 达标，验收通过。"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "evaluated"
        assert resp.json()["active_claim_id"] is not None

        # 时段 S 已占用：I2 的候选列表看不到 S 的报告，并发验收只能失败。
        options = client.get(f"/improvements/{i2['id']}/comparisons", headers=_auth(client, "analyst")).json()
        assert all(item["department_slot_id"] != slot_s.id for item in options)
        resp = client.post(f"/improvements/{i2['id']}/evaluate", headers=_auth(client, "reviewer"),
                           json={"comparison_report_id": r2.id, "evaluation_note": "尝试同时段并发验收。"})
        assert resp.status_code == 409
        assert "占用" in resp.json()["detail"]

        # I1 撤回：结论快照留档、时段释放、事项回到待验收。
        resp = client.post(f"/improvements/{i1['id']}/withdraw", headers=_auth(client, "reviewer"),
                           json={"withdrawal_note": "复测样本需要补充核对，先撤回。"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "implemented"
        assert body["comparison_report_id"] is None
        assert body["comparison_p90"] is None
        assert body["withdrawn_count"] == 1
        assert body["active_claim_id"] is None

        history = client.get("/improvement-evaluation-history", headers=_auth(client, "analyst")).json()
        mine = [row for row in history if row["improvement_id"] == i1["id"]]
        assert len(mine) == 1
        assert mine[0]["comparison_report_id"] == r1.id
        assert mine[0]["evaluation_note"] == "P90 达标，验收通过。"
        assert mine[0]["withdrawal_note"] == "复测样本需要补充核对，先撤回。"
        assert mine[0]["evaluated_by_name"] == "科室复核员"
        assert mine[0]["outcome"] == "met"

        # 时段重新可选：I2 用重做版报告验收成功，占用同个时段 S。
        options = client.get(f"/improvements/{i2['id']}/comparisons", headers=_auth(client, "analyst")).json()
        assert {item["id"] for item in options} >= {r1.id, r2.id}
        resp = client.post(f"/improvements/{i2['id']}/evaluate", headers=_auth(client, "reviewer"),
                           json={"comparison_report_id": r2.id, "evaluation_note": "使用重做报告验收。"})
        assert resp.status_code == 200, resp.text

        claims = client.get("/improvement-slot-claims", headers=_auth(client, "analyst")).json()["claims"]
        slot_claims = [c for c in claims if c["department_slot_id"] == slot_s.id]
        assert len(slot_claims) == 1
        assert slot_claims[0]["improvement_id"] == i2["id"]
        assert slot_claims[0]["report_id"] == r2.id
        # I1 的原结论（第一版报告）仍可在撤回记录中查阅。
        history = client.get("/improvement-evaluation-history", headers=_auth(client, "analyst")).json()
        assert any(row["improvement_id"] == i1["id"] and row["comparison_report_id"] == r1.id for row in history)
    finally:
        db.close()


def test_database_unique_constraint_blocks_concurrent_claims(client):
    """规则 2：数据库层保证同一时段同时只有一个活跃占用。"""
    db = SessionLocal()
    try:
        i1 = _make_improvement(client, db, "消化内科", 10, 35)
        i2 = _make_improvement(client, db, "消化内科", 11, 30)
        analyst = db.query(User).filter_by(username="analyst").first()
        reviewer = db.query(User).filter_by(username="reviewer").first()
        slot_s = _comparison_slot(db, "消化内科", 17, [11, 13, 16, 22])
        r1 = _reviewed_report(db, slot_s, "消化内科复测一", analyst, reviewer)
        r2 = _reviewed_report(db, slot_s, "消化内科复测二", analyst, reviewer)

        ok = client.post(f"/improvements/{i1['id']}/evaluate", headers=_auth(client, "reviewer"),
                         json={"comparison_report_id": r1.id, "evaluation_note": "第一项通过。"})
        assert ok.status_code == 200

        # 另一个会话直接插入同 slot 占用，必须被唯一索引拒绝。
        db.add(ImprovementSlotClaim(improvement_id=i2["id"], department_slot_id=slot_s.id,
                                    report_id=r2.id, claimed_by=reviewer.id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # 一个事项同时只能持有一个时段占用。
        other = _comparison_slot(db, "消化内科", 18, [10, 11, 14, 19])
        r3 = _reviewed_report(db, other, "消化内科其他时段", analyst, reviewer)
        db.add(ImprovementSlotClaim(improvement_id=i1["id"], department_slot_id=other.id,
                                    report_id=r3.id, claimed_by=reviewer.id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_stale_withdrawal_never_releases_another_improvements_claim(client):
    """规则 5：旧撤回重试不会释放已被其他事项认领的时段。"""
    db = SessionLocal()
    try:
        i3 = _make_improvement(client, db, "内分泌科", 10, 35)
        i4 = _make_improvement(client, db, "内分泌科", 11, 30)
        analyst = db.query(User).filter_by(username="analyst").first()
        reviewer = db.query(User).filter_by(username="reviewer").first()
        slot_t = _comparison_slot(db, "内分泌科", 16, [9, 10, 14, 18])
        r1 = _reviewed_report(db, slot_t, "内分泌复测一", analyst, reviewer)
        r2 = _reviewed_report(db, slot_t, "内分泌复测二", analyst, reviewer)

        # I3 验收后撤回，释放 T。
        assert client.post(f"/improvements/{i3['id']}/evaluate", headers=_auth(client, "reviewer"),
                           json={"comparison_report_id": r1.id, "evaluation_note": "I3 验收。"}).status_code == 200
        assert client.post(f"/improvements/{i3['id']}/withdraw", headers=_auth(client, "reviewer"),
                           json={"withdrawal_note": "I3 撤回。"}).status_code == 200

        # I4 认领 T。
        assert client.post(f"/improvements/{i4['id']}/evaluate", headers=_auth(client, "reviewer"),
                           json={"comparison_report_id": r2.id, "evaluation_note": "I4 验收。"}).status_code == 200

        # 旧撤回重试：I3 已回到 implemented，撤回接口直接 409。
        stale = client.post(f"/improvements/{i3['id']}/withdraw", headers=_auth(client, "reviewer"),
                            json={"withdrawal_note": "重试旧撤回。"})
        assert stale.status_code == 409

        # 即使按 I3 条件重放删除语句，也删不到 I4 持有的占用。
        deleted = db.query(ImprovementSlotClaim).filter(
            ImprovementSlotClaim.improvement_id == i3["id"]).delete(synchronize_session=False)
        db.commit()
        assert deleted == 0
        active = db.query(ImprovementSlotClaim).filter_by(department_slot_id=slot_t.id).one()
        assert active.improvement_id == i4["id"]

        # I3 重新验收别的时段不受影响；T 仍只被 I4 占用。
        other = _comparison_slot(db, "内分泌科", 17, [8, 9, 12, 16])
        r3 = _reviewed_report(db, other, "内分泌其他时段", analyst, reviewer)
        again = client.post(f"/improvements/{i3['id']}/evaluate", headers=_auth(client, "reviewer"),
                            json={"comparison_report_id": r3.id, "evaluation_note": "I3 重新验收。"})
        assert again.status_code == 200
        assert db.query(ImprovementSlotClaim).filter_by(department_slot_id=slot_t.id).one().improvement_id == i4["id"]
    finally:
        db.close()


def test_claims_endpoint_lists_available_slots_occupiers_and_history(client):
    """规则 6：追踪页能查到可选时段、占用方和撤回记录。"""
    db = SessionLocal()
    try:
        i5 = _make_improvement(client, db, "骨科", 10, 35)
        analyst = db.query(User).filter_by(username="analyst").first()
        reviewer = db.query(User).filter_by(username="reviewer").first()
        occupied_slot = _comparison_slot(db, "骨科", 16, [10, 12, 15, 20])
        free_slot = _comparison_slot(db, "骨科", 17, [11, 12, 16, 21])
        r_occ = _reviewed_report(db, occupied_slot, "骨科复测占用", analyst, reviewer)
        r_free = _reviewed_report(db, free_slot, "骨科复测可选", analyst, reviewer)
        assert client.post(f"/improvements/{i5['id']}/evaluate", headers=_auth(client, "reviewer"),
                           json={"comparison_report_id": r_occ.id, "evaluation_note": "骨科验收。"}).status_code == 200
        assert client.post(f"/improvements/{i5['id']}/withdraw", headers=_auth(client, "reviewer"),
                           json={"withdrawal_note": "骨科撤回留档。"}).status_code == 200
        # 再验收一次，制造一条活跃占用和一条历史。
        assert client.post(f"/improvements/{i5['id']}/evaluate", headers=_auth(client, "reviewer"),
                           json={"comparison_report_id": r_free.id, "evaluation_note": "骨科再次验收。"}).status_code == 200

        data = client.get("/improvement-slot-claims", headers=_auth(client, "analyst")).json()
        claim = next(c for c in data["claims"] if c["improvement_id"] == i5["id"])
        assert claim["department_slot_id"] == free_slot.id
        assert claim["claimed_by_name"] == "科室复核员"
        assert claim["report_code"] == r_free.report_code
        assert claim["improvement_status"] == "evaluated"

        available_ids = {s["slot_id"] for s in data["available_slots"]}
        assert free_slot.id not in available_ids  # 被占用
        # 曾占用后撤回的时段，当前无占用且报告合格，应重新出现在可选清单。
        entry = next(s for s in data["available_slots"] if s["slot_id"] == occupied_slot.id)
        assert entry["department_name"] == "骨科"
        assert any(r["id"] == r_occ.id for r in entry["reports"])

        history = client.get("/improvement-evaluation-history", headers=_auth(client, "analyst")).json()
        rows = [h for h in history if h["improvement_id"] == i5["id"]]
        assert len(rows) == 1
        assert rows[0]["comparison_report_id"] == r_occ.id
        assert rows[0]["withdrawn_by_name"] == "科室复核员"
        assert rows[0]["slot_label"] == "随访加开窗"

        listed = client.get("/improvements", headers=_auth(client, "analyst")).json()
        card = next(item for item in listed if item["id"] == i5["id"])
        assert card["withdrawn_count"] == 1
        assert card["active_claim_id"] is not None
    finally:
        db.close()


def test_withdraw_requires_review_role(client):
    """规则 4 的权限面：撤回属于复核动作，分析专员无权执行。"""
    db = SessionLocal()
    try:
        i6 = _make_improvement(client, db, "普外科", 10, 35)
        analyst = db.query(User).filter_by(username="analyst").first()
        reviewer = db.query(User).filter_by(username="reviewer").first()
        slot = _comparison_slot(db, "普外科", 16, [9, 10, 13, 17])
        report = _reviewed_report(db, slot, "普外科复测", analyst, reviewer)
        assert client.post(f"/improvements/{i6['id']}/evaluate", headers=_auth(client, "reviewer"),
                           json={"comparison_report_id": report.id, "evaluation_note": "普外科验收。"}).status_code == 200
        denied = client.post(f"/improvements/{i6['id']}/withdraw", headers=_auth(client, "analyst"),
                             json={"withdrawal_note": "越权撤回尝试。"})
        assert denied.status_code == 403
        still_evaluated = client.get("/improvements", headers=_auth(client, "analyst")).json()
        assert next(item for item in still_evaluated if item["id"] == i6["id"])["status"] == "evaluated"
    finally:
        db.close()
