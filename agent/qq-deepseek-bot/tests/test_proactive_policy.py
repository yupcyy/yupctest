from qq_deepseek.services.proactive_policy import ProactivePolicy


def test_dnd_budget_unanswered_and_reply():
    policy = ProactivePolicy()
    assert policy.reserve("private:1", 0)  # 08:00 CST
    now = 3600
    assert policy.reserve("private:1", now)
    assert policy.reserve("private:1", now + 14400)
    policy.answered("private:1")
    assert not policy.reserve("private:1", now + 43200)  # daily cap remains three
    policy.answered("private:1")
    assert not policy.reserve("private:1", now + 44000)


def test_group_caps_three_unanswered_and_reset():
    policy = ProactivePolicy()
    target = "group:1077893032"
    assert policy.reserve(target, 3600, group=True)
    assert policy.reserve(target, 3600, group=True)
    assert policy.reserve(target, 3600, group=True)
    assert not policy.reserve(target, 3601, group=True)
    policy.answered(target)
    assert policy.reserve(target, 3601, group=True)


def test_group_daily_limits_and_hours():
    policy = ProactivePolicy()
    target = "group:1077893032"
    for _ in range(20):
        policy.answered(target)
        assert policy.reserve(target, 3600, group=True)
    policy.answered(target)
    assert not policy.reserve(target, 3600, group=True)
    assert not ProactivePolicy().reserve(target, 18 * 3600, group=True)  # 02:00 CST


def test_private_all_day_two_unanswered_four_hour_cooldown():
    policy = ProactivePolicy()
    night = 18 * 3600  # 02:00 CST
    assert policy.reserve("private:1", night)
    assert policy.reserve("private:1", night + 1)
    assert not policy.reserve("private:1", night + 14399)
    assert policy.reserve("private:1", night + 14401)
