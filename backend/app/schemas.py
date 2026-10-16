from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class DataSourceConfig(BaseModel):
    db_type: str = Field(..., description="mysql / postgresql / sqlite / oceanbase / oracle / dameng")
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: Optional[str] = None
    schema_name: Optional[str] = None
    # OceanBase only: auto / mysql / oracle
    ob_mode: Optional[str] = Field(default="auto", description="OceanBase 租户模式: auto / mysql / oracle")


class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    source: DataSourceConfig
    target: DataSourceConfig


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    source: Optional[DataSourceConfig] = None
    target: Optional[DataSourceConfig] = None
    session_state: Optional[Any] = None
    status: Optional[str] = None
    report: Optional[Any] = None


class TaskCopyRequest(BaseModel):
    task_id: int


class ConnectionTestRequest(BaseModel):
    config: DataSourceConfig


class TaskOut(BaseModel):
    id: int
    name: str
    source: dict
    target: dict
    status: str = "in_progress"
    report: Optional[Any] = None
    created_at: datetime
    updated_at: datetime
    session_state: Optional[Any] = None

    class Config:
        from_attributes = True


class ColumnPair(BaseModel):
    source: str
    target: str
    source_table: Optional[str] = None
    # 多源字段聚合到同一目标时的物理列，如 ["periodicity", "time_unit"]
    # 对比时按顺序用 "+" 拼接；为空则退回 source 单列
    source_fields: list[str] = Field(default_factory=list)


class ValueAlias(BaseModel):
    source_field: str
    source_value: str
    target_field: str
    target_value: str


class ExtractMatchRule(BaseModel):
    """Extract characters by 1-based positions then exact-compare.

    Position spec examples:
    - "1245" -> positions 1,2,4,5 (from start)
    - "-1245" -> -1,-2,-4,-5 (from end, -1 = last char)
    - "4,5,7,8" / "-5,-4,-2,-1" -> explicit list
    """

    source_field: str
    source_positions: str
    target_field: str
    target_positions: str


class SourceJoinSpec(BaseModel):
    left_table: str
    left_field: str
    right_table: str
    right_field: str


class MatchPairRef(BaseModel):
    source_database: str
    target_database: str
    source_table: str
    target_table: str
    source_schema: Optional[str] = None
    target_schema: Optional[str] = None


class SearchCondition(BaseModel):
    search_columns: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    # include=包含, exclude=不包含, equals=等于, not_equals=不等于
    mode: str = "include"
    negate: bool = False
    # 与上一条条件的关系：and=且, or=或（首条忽略）
    logic: str = "and"


class RowMatchRequest(MatchPairRef):
    columns: list[ColumnPair]
    value_aliases: list[ValueAlias] = Field(default_factory=list)
    extract_match_rules: list[ExtractMatchRule] = Field(default_factory=list)
    source_joins: list[SourceJoinSpec] = Field(default_factory=list)
    fuzzy_content_match: bool = False
    source_conditions: list[SearchCondition] = Field(default_factory=list)
    target_conditions: list[SearchCondition] = Field(default_factory=list)
    # and=全部满足, or=任一满足
    source_condition_logic: str = "and"
    target_condition_logic: str = "and"


class RowMatchOverlayRequest(MatchPairRef):
    source_indices: list[int] = Field(default_factory=list)
    target_indices: list[int] = Field(default_factory=list)


class UnmatchedRowsRequest(MatchPairRef):
    side: str
    database: str
    table: str
    schema_name: Optional[str] = None
    offset: int = 0
    limit: int = 100


class SearchRowsRequest(MatchPairRef):
    side: str
    database: str
    table: str
    schema_name: Optional[str] = None
    keyword: str = ""
    keywords: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    search_columns: Optional[list[str]] = None
    negate: bool = False
    conditions: list[SearchCondition] = Field(default_factory=list)
    # and=全部满足, or=任一满足
    condition_logic: str = "and"
    offset: int = 0
    limit: int = 100
    unmatched_only: bool = False
    source_joins: list[SourceJoinSpec] = Field(default_factory=list)


class RowMatchEditRequest(MatchPairRef):
    action: str
    source: Optional[int] = None
    target: Optional[int] = None


class RowsByIndicesRequest(BaseModel):
    side: str
    database: str
    table: str
    schema_name: Optional[str] = None
    indices: list[int]


class ExportRowsRequest(MatchPairRef):
    """Export filtered source/target rows to a 2-sheet Excel workbook."""

    source_columns: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)
    source_conditions: list[SearchCondition] = Field(default_factory=list)
    target_conditions: list[SearchCondition] = Field(default_factory=list)
    source_condition_logic: str = "and"
    target_condition_logic: str = "and"
    source_joins: list[SourceJoinSpec] = Field(default_factory=list)
    unmatched_only: bool = False
    # safety cap per sheet
    limit: int = 50000



class RowsByColumnValuesRequest(BaseModel):
    side: str
    database: str
    table: str
    column: str
    values: list[Any]
    schema_name: Optional[str] = None
    limit: int = 2000


class DatabaseQuery(BaseModel):
    side: str = Field(..., description="source or target")
    database: Optional[str] = None
    schema_name: Optional[str] = None
    table: Optional[str] = None
    limit: int = 100
    offset: int = 0
    column: Optional[str] = None
