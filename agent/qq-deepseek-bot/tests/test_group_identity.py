from qq_deepseek.services.group_identity import GroupIdentity


def test_group_scoped_names_and_ambiguity():
    index = GroupIdentity()
    index.observe(1, 10, {'nickname': '小明', 'card': '明哥'}, 'hello')
    assert index.resolve(1, '明哥怎么样')[0] == (10,)
    assert index.resolve(2, '明哥怎么样')[0] == ()
    index.observe(1, 20, {'nickname': '小明'}, 'hi')
    ids, ambiguous = index.resolve(1, '小明怎么样')
    assert not ids and ambiguous == ('小明',)
    assert 'QQ=10' in index.context(1)
