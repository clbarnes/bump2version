import re
from abc import ABC, abstractmethod
from functools import total_ordering
from typing import NamedTuple, Optional, Tuple
import enum
from string import ascii_letters, digits


class StrEnum(str, enum.Enum):
    def __new__(cls, *args):
        for arg in args:
            if not isinstance(arg, (str, enum.auto)):
                raise TypeError(
                    "Values of StrEnums must be strings: {} is a {}".format(
                        repr(arg), type(arg)
                    )
                )
        return super().__new__(cls, *args)

    def __str__(self):
        return self.value

    # pylint: disable=no-self-argument
    # The first argument to this function is documented to be the name of the
    # enum member, not `self`:
    # https://docs.python.org/3.6/library/enum.html#using-automatic-values
    def _generate_next_value_(name, *_):
        return name


def is_pos_int(n) -> bool:
    return isinstance(n, int) and n >= 0


def validate(obj):
    if obj is not None:
        obj.validate()


@total_ordering
class Comparable(ABC):
    @abstractmethod
    def _comparable(self) -> "Comparable":
        pass

    def _compare(self, other):
        try:
            return _compare(self, other)
        except TypeError:
            return _compare(self._comparable(), other._comparable())
        finally:
            raise TypeError(f"Could not compare {type(self)} with {type(other)}")



@total_ordering
class SubreleaseType(StrEnum):
    ALPHA = "a"
    BETA = "b"
    RELEASE_CANDIDATE = "rc"
    POST = "post"

    @classmethod
    def order(cls, obj) -> Optional[float]:
        try:
            obj = SubreleaseType(obj)
        except ValueError:
            return 2.5

        return list(SubreleaseType).index(obj)

    def __lt__(self, other):
        return SubreleaseType.order(self) < SubreleaseType.order(other)

    def __le__(self, other):
        return SubreleaseType.order(self) <= SubreleaseType.order(other)

    def __ge__(self, other):
        return SubreleaseType.order(self) >= SubreleaseType.order(other)

    def __gt__(self, other):
        return SubreleaseType.order(self) > SubreleaseType.order(other)

    def is_pre(self):
        return self != SubreleaseType.POST


class Subrelease(NamedTuple):
    type: SubreleaseType
    number: int

    def validate(self):
        if not is_pos_int(self.number):
            raise ValueError("Subrelease is not a positive integer")

    def __str__(self):
        return f"{self.type}{self.number}"

    def __gt__(self, other):
        if other is None:
            return other.is_pre()
        elif isinstance(other, Subrelease):
            return other > self
        else:
            return NotImplemented

    def __ge__(self, other):
        return self == other or self > other

    def __lt__(self, other):
        return not (self >= other)

    def __le__(self, other):
        return self == other or self < other


class Mutatable:
    def mutate(self, key, value):
        d = self._asdict()
        d[key] = value
        return type(self)(**d)


class Release(tuple, Mutatable):
    def mutate(self, key, value) -> "Release":
        lst = list(self)
        lst[key] = value
        return Release(lst)

    def validate(self):
        if len(self) < 1:
            raise ValueError("Release must have at least one part")
        for item in self:
            if not is_pos_int(item):
                raise ValueError("Release parts must be positive integers")

    @property
    def major(self) -> Optional[int]:
        return self[0]

    @property
    def minor(self) -> Optional[int]:
        return self[1] if len(self) > 1 else None

    @property
    def patch(self) -> Optional[int]:
        return self[2] if len(self) > 2 else None

    @property
    def subpatch(self) -> Tuple[int, ...]:
        return tuple() if len(self) < 4 else self[3:]

    def triple(self) -> "Release":
        lst = list(self[:3])
        while len(lst) < 3:
            lst.append(0)
        return Release(lst)

    def __str__(self) -> str:
        return ".".join(str(n) for n in self)

    def bump(self, index, step=1) -> "Release":
        if index < len(self):
            return self.mutate(index, self[index] + step)
        elif step > 0:
            parts = list(self)
            while len(parts) < index:
                parts.append(0)
            parts.append(step)
            return Release(parts)
        else:
            raise ValueError("Nonexistent part cannot be decremented")


class FinalVersion(NamedTuple, Mutatable):
    epoch: Optional[int] = None
    release: Release = (0,)

    def validate(self):
        if self.epoch is not None and not is_pos_int(self.epoch):
            raise ValueError("epoch is not a positive integer")

        self.release.validate()

    def __str__(self) -> str:
        segments = []
        if self.epoch is not None:
            segments.append(str(self.epoch))
        segments.append(".".join(str(part) for part in self.release))
        return "!".join(segments)

    def _comparable(self) -> "FinalVersion":
        out = self
        if out.epoch is None:
            out = out.mutate("epoch", 0)
        return out


class PublicVersion(NamedTuple, Mutatable):
    epoch: Optional[int] = None
    release: Release = Release((0,))
    subrelease: Optional[Subrelease] = None
    dev: Optional[int] = None

    def validate(self):
        self.final().validate()
        self.subrelease.validate()
        if self.dev is not None and not is_pos_int(self.dev):
            raise ValueError("Dev release is not a positive integer")

    def final(self) -> FinalVersion:
        return FinalVersion(self.epoch, self.release)

    def __str__(self) -> str:
        return f"{self.final()}.{self.subrelease}"

    def _comparable(self) -> "PublicVersion":
        out = self
        if out.epoch is None:
            out = out.mutate("epoch", 0)
        if out.dev is None:
            out = out.mutate("dev", -1)
        return out


local_chars = set(ascii_letters + digits + ".")


VERSION_PATTERN = r"""
    (?:
        (?:(?P<epoch>[0-9]+)!)?            # epoch
        (?P<release>[0-9]+(?:\.[0-9]+)*)   # release segment
        (\.
            (?P<sub_type>a|b|rc|post)      # subrelease type
            (?P<sub_number>[0-9]+)         # subrelease number
        )?
        (\.dev(?P<dev>[0-9]+)?             # dev number
    )
    (?:\+(?P<local>[a-zA-Z0-9]*))?         # local version
"""
version_re = re.compile(r"^\s*" + VERSION_PATTERN + r"\s*$", re.VERBOSE)


class Version(NamedTuple, Mutatable):
    epoch: Optional[int] = None
    release: Release = Release((0,))
    subrelease: Optional[Subrelease] = None
    dev: Optional[int] = None
    local: Optional[str] = None

    def validate(self):
        self.public().validate()
        if self.local is None:
            return
        if not local_chars.issuperset(self.local):
            raise ValueError("local label includes invalid characters")
        if "." in (self.local[0], self.local[-1]):
            raise ValueError("local label starts or ends with period")

    def public(self) -> PublicVersion:
        return PublicVersion(self.epoch, self.release, self.subrelease)

    def final(self) -> FinalVersion:
        return self.public().final()

    def __str__(self) -> str:
        segments = [str(self.public())]
        if self.local is not None:
            segments.append(self.local)
        return "+".join(segments)

    @classmethod
    def parse(cls, s) -> "Version":
        match = version_re.match(s)
        if match is None:
            raise ValueError("String did not match version constraints")
        g = match.groupdict()
        epoch_str = g.get("epoch")
        epoch = int(epoch_str) if epoch_str else None
        release = Release(int(n) for n in g.get("release").split("."))
        subrelease_type = g.get("subrelease_type")
        if subrelease_type:
            subrelease = Subrelease(
                SubreleaseType(subrelease_type), int(g["subrelease_number"])
            )
        else:
            subrelease = None
        dev_str = g.get("dev")
        dev = int(dev_str) if dev_str else None

        v = Version(epoch, release, subrelease, dev, g.get("local"))
        v.validate()
        return v

    def _comparable(self) -> "Version":
        out = self
        if out.epoch is None:
            out = out.mutate("epoch", 0)
        if out.dev is None:
            out = out.mutate("dev", -1)
        if out.local is None:
            out = out.mutate("local", "")
        return out


def _compare(first, second):
    if first == second:
        return 0
    if first > second:
        return 1
    if first < second:
        return -1


def compare(first, second):
    try:
        return _compare(first, second)
    except TypeError as e:
        try:
            first = first._comparable()
            second = second._comparable()
        except AttributeError:
            raise e
        return _compare(first, second)
