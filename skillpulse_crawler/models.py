from datetime import date
from typing import Optional, Literal, Union
from pydantic import BaseModel, Field, field_validator, ConfigDict

Section = Literal["news", "project", "paper", "community"]


class WeeklyDigestItem(BaseModel):
    """与后端 ItemDto / WeeklyDigestItem 严格对齐字段命名
    使用 by_alias=True 序列化时输出 camelCase，匹配 Java 后端约定
    """
    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    id: str = ""
    section: Section
    title: str = Field(max_length=500)
    summary: Optional[str] = None
    url: str = Field(max_length=1000)
    source: str
    source_id: str = Field(alias="sourceId")
    stars: Optional[int] = None
    comments_count: Optional[int] = Field(default=None, alias="commentsCount")
    likes_count: Optional[int] = Field(default=None, alias="likesCount")
    published_date: Optional[date] = Field(default=None, alias="publishedDate")

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must start with http(s)://")
        return v

    def with_generated_id(self) -> "WeeklyDigestItem":
        if not self.id:
            object.__setattr__(self, "id", f"{self.section}-{self.source}-{self.source_id}")
        return self


FetcherType = Literal["rss", "http", "api"]
ExtractorType = Literal["xpath", "jsonpath", "regex", "rss"]


class FetcherConfig(BaseModel):
    type: FetcherType
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_sec: int = 20


class ExtractorField(BaseModel):
    expr: str
    parser: Optional[str] = None


class ExtractorConfig(BaseModel):
    type: ExtractorType
    item_selector: Optional[str] = None
    fields: dict[str, Union[str, ExtractorField]] = Field(default_factory=dict)


class MappingConfig(BaseModel):
    source: str
    source_id: ExtractorField
    published_date: Optional[ExtractorField] = None


class LimitConfig(BaseModel):
    raw: int = 30
    top: int = 10


class RankConfig(BaseModel):
    formula: Literal["recency", "stars", "custom"] = "recency"
    weight_recency: float = 0.6
    weight_engagement: float = 0.4


class SourceConfig(BaseModel):
    id: str
    section: Section
    display_name: str = ""
    enabled: bool = True
    interval: Literal["weekly", "daily", "manual"] = "weekly"
    fetcher: FetcherConfig
    extractor: ExtractorConfig
    mapping: MappingConfig
    limit: LimitConfig = Field(default_factory=LimitConfig)
    rank: RankConfig = Field(default_factory=RankConfig)
    filter: dict = Field(default_factory=dict)