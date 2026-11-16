from enum import Enum
import re

from pydantic import BaseModel, Field, field_validator


class EntityType(str, Enum):
    ErrorCode = "ErrorCode"
    Service = "Service"
    Team = "Team"
    Person = "Person"
    Channel = "Channel"
    Plan = "Plan"
    Policy = "Policy"
    Feature = "Feature"
    Version = "Version"


class RelationType(str, Enum):
    RAISED_BY = "RAISED_BY"
    OWNS = "OWNS"
    ESCALATES_TO = "ESCALATES_TO"
    CONTACT_VIA = "CONTACT_VIA"
    MEMBER_OF = "MEMBER_OF"
    LEADS = "LEADS"
    APPLIES_TO = "APPLIES_TO"
    PART_OF = "PART_OF"
    REPLACES = "REPLACES"
    DEPENDS_ON = "DEPENDS_ON"


class Entity(BaseModel):
    name: str = Field(min_length=1)
    type: EntityType

    @field_validator("name")
    @classmethod
    def non_empty_name(cls, value):
        if not value.strip():
            raise ValueError("Entity name must not be blank")
        return value


class Triple(BaseModel):
    subject: Entity
    relation: RelationType
    object: Entity


class Extraction(BaseModel):
    triples: list[Triple]


class GenericEntityType(str, Enum):
    Person = "Person"
    Organization = "Organization"
    Team = "Team"
    Product = "Product"
    Service = "Service"
    Tool = "Tool"
    Concept = "Concept"
    Process = "Process"
    Event = "Event"
    Place = "Place"
    Document = "Document"
    Other = "Other"


class GenericEntity(BaseModel):
    name: str = Field(min_length=1)
    type: GenericEntityType

    @field_validator("name")
    @classmethod
    def non_blank_name(cls, value):
        if not value.strip():
            raise ValueError("Entity name must not be blank")
        return value


class GenericTriple(BaseModel):
    subject: GenericEntity
    relation: str
    object: GenericEntity

    @field_validator("relation")
    @classmethod
    def normalize_relation(cls, value):
        value = value.strip().upper().replace(" ", "_").replace("-", "_")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,39}", value):
            raise ValueError("Relation must be 2–40 characters in UPPER_SNAKE_CASE")
        return value


class GenericExtraction(BaseModel):
    triples: list[GenericTriple]
