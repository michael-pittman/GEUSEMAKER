from __future__ import annotations

from geusemaker.services.cost import ResourceTagger


class FakeEC2:
    def __init__(self) -> None:
        self.tags = None
        self.resources = None

    def create_tags(self, Resources: list[str], Tags: list[dict[str, str]]) -> dict:  # noqa: N803
        self.resources = Resources
        self.tags = Tags
        return {"ok": True}


class FakeEFS:
    def __init__(self) -> None:
        self.tags = None
        self.file_system_id = None

    def create_tags(self, FileSystemId: str, Tags: list[dict[str, str]]) -> dict:  # noqa: N803
        self.file_system_id = FileSystemId
        self.tags = Tags
        return {"ok": True}


class FakeELBv2:
    def __init__(self) -> None:
        self.arns = None
        self.tags = None

    def add_tags(self, ResourceArns: list[str], Tags: list[dict[str, str]]) -> dict:  # noqa: N803
        self.arns = ResourceArns
        self.tags = Tags
        return {"ok": True}


class FakeFactory:
    def __init__(self) -> None:
        self.ec2 = FakeEC2()
        self.efs = FakeEFS()
        self.elb = FakeELBv2()

    def get_client(self, service_name: str, region: str = "us-east-1") -> object:  # noqa: ARG002
        if service_name == "ec2":
            return self.ec2
        if service_name == "efs":
            return self.efs
        if service_name == "elbv2":
            return self.elb
        raise KeyError(service_name)


def test_resource_tagger_builds_and_applies_tags() -> None:
    factory = FakeFactory()
    tagger = ResourceTagger(factory)
    tags = tagger.build_tags("stack", "dev")
    assert any(tag["Key"] == "geusemaker:deployment" for tag in tags)

    tagger.tag_instances(["i-123"], tags)
    assert factory.ec2.tags == tags

    tagger.tag_efs("fs-123", tags)
    assert factory.efs.file_system_id == "fs-123"

    tagger.tag_alb("arn:aws:elasticloadbalancing:::alb/123", tags)
    assert factory.elb.tags == tags
