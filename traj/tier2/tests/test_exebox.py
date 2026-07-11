from types import SimpleNamespace

from traj.tier2 import exebox


def test_box_names_are_prefixed_lowercase_and_bounded():
    name = exebox.box_name_for_instance("Django__Django-12345_This_Is_Long")

    assert name.startswith("t2-")
    assert name == name.lower()
    assert len(name) <= 20
    assert "__" not in name


def test_wait_ready_polls_ssh_until_ready():
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        stdout = "" if len(calls) == 1 else "READY\n"
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    client = exebox.ExeBoxClient(runner=runner, requester=lambda command, key: {})

    client.wait_ready("t2-ready", poll_s=0, timeout_s=5)

    assert len(calls) == 2
    assert calls[0][:7] == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "t2-ready.exe.xyz",
        "--",
    ]


def test_cleanup_removes_only_runner_created_boxes():
    removed = []

    def requester(command, key):
        if command == "ls":
            return [{"name": "t2-one"}, {"name": "manual"}, "t2-two"]
        if command.startswith("rm "):
            removed.append(command.removeprefix("rm "))
            return {"ok": True}
        raise AssertionError(command)

    client = exebox.ExeBoxClient(runner=lambda *args, **kwargs: None, requester=requester, key="test-key")

    assert client.cleanup() == ["t2-one", "t2-two"]
    assert removed == ["t2-one", "t2-two"]
