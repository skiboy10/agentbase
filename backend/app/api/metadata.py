"""
Metadata schema management API.

Provides CRUD for knowledge metadata schemas — user-defined field definitions
that enable structured metadata on knowledge sources and filtered search.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey, SourceMetadataSchema

router = APIRouter()


class MetadataSchemaCreate(BaseModel):
    name: str
    description: Optional[str] = None
    fields: dict  # {"field_name": {"type": "string", "required": false, "indexed": true, "values": [...]}}


class MetadataSchemaUpdate(BaseModel):
    description: Optional[str] = None
    fields: Optional[dict] = None  # Additive only — new fields can be added


class MetadataSchemaResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    fields: dict
    created_at: Optional[str]


def _schema_to_response(schema: SourceMetadataSchema) -> dict:
    return {
        "id": schema.id,
        "name": schema.name,
        "description": schema.description,
        "fields": schema.fields,
        "created_at": schema.created_at.isoformat() if schema.created_at else None,
    }


@router.get("/schemas")
async def list_schemas(
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List all metadata schemas."""
    stmt = select(SourceMetadataSchema).order_by(SourceMetadataSchema.name)
    result = await db.execute(stmt)
    schemas = result.scalars().all()
    return [_schema_to_response(s) for s in schemas]


@router.post("/schemas", status_code=201)
async def create_schema(
    body: MetadataSchemaCreate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Create a new metadata schema."""
    # Check for duplicate name
    existing = await db.execute(
        select(SourceMetadataSchema).where(SourceMetadataSchema.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Schema '{body.name}' already exists")

    schema = SourceMetadataSchema(
        name=body.name,
        description=body.description,
        fields=body.fields,
    )
    db.add(schema)
    await db.flush()
    return _schema_to_response(schema)


@router.get("/schemas/{schema_id}")
async def get_schema(
    schema_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get a metadata schema by ID."""
    stmt = select(SourceMetadataSchema).where(SourceMetadataSchema.id == schema_id)
    result = await db.execute(stmt)
    schema = result.scalar_one_or_none()
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")
    return _schema_to_response(schema)


@router.put("/schemas/{schema_id}")
async def update_schema(
    schema_id: str,
    body: MetadataSchemaUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Update a metadata schema. Fields can only be added, not removed."""
    stmt = select(SourceMetadataSchema).where(SourceMetadataSchema.id == schema_id)
    result = await db.execute(stmt)
    schema = result.scalar_one_or_none()
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")

    if body.description is not None:
        schema.description = body.description

    if body.fields is not None:
        # Merge new fields into existing — never remove existing fields
        merged = {**schema.fields, **body.fields}
        schema.fields = merged

    await db.flush()
    return _schema_to_response(schema)
