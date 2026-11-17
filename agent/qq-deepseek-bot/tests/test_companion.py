from qq_deepseek.services.companion import Companion


def test_emotion_decay_and_scope_privacy():
    now = [100.0]
    service = Companion(lambda: now[0])
    for _ in range(4):
        service.observe("private:1", 1, "谢谢 抱抱")
    assert "开心" in service.hint("private:1")
    assert service.hint("group:2") == ""
    now[0] += 86400
    assert "平静" in service.hint("private:1")


def test_activity_expiry_and_bounded_storage():
    now = [100.0]
    service = Companion(lambda: now[0])
    for i in range(16):
        service.observe("group:1", i % 3, "聊天")
    assert service.atmosphere("group:1") == "热闹"
    now[0] += 601
    assert service.atmosphere("group:1") == "安静"
    for i in range(600):
        service.observe(str(i), i, "秘密文字")
    assert len(service.moods) == len(service.activity) == 512
    assert "秘密文字" not in repr(service.activity)
