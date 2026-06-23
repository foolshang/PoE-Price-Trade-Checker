"""OCR result data structures."""
from dataclasses import dataclass, field


@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


@dataclass
class WordResult:
    text: str
    bbox: BoundingBox
    confidence: float = 1.0


@dataclass
class LineResult:
    text: str
    words: list[WordResult] = field(default_factory=list)

    @property
    def bbox(self) -> BoundingBox:
        if not self.words:
            return BoundingBox(0, 0, 0, 0)
        xs = [w.bbox.x for w in self.words]
        ys = [w.bbox.y for w in self.words]
        rights = [w.bbox.right for w in self.words]
        bottoms = [w.bbox.bottom for w in self.words]
        return BoundingBox(min(xs), min(ys), max(rights) - min(xs), max(bottoms) - min(ys))


@dataclass
class OcrResult:
    lines: list[LineResult] = field(default_factory=list)

    @property
    def words(self) -> list[WordResult]:
        return [w for line in self.lines for w in line.words]

    @property
    def full_text(self) -> str:
        return "\n".join(line.text for line in self.lines)
