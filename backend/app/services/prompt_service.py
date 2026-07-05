"""
Prompt Service - Manages system prompts for agent task types.

This service provides:
- Prompt CRUD operations
- Default prompt resolution (project-level or global)
- Prompt versioning support
"""
from typing import Optional
from dataclasses import dataclass
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Prompt, Project

logger = structlog.get_logger()


# Default RAG context template used when prompt doesn't specify one
DEFAULT_RAG_CONTEXT_TEMPLATE = """## Relevant Documentation

The following documentation excerpts may help answer the user's question:

{context}

---

Use this documentation to provide accurate, sourced answers. If the documentation doesn't cover the question, you may use your general knowledge but indicate when you're doing so."""


@dataclass
class PromptInfo:
    """Prompt information returned from service."""
    id: str
    project_id: Optional[str]
    name: str
    description: Optional[str]
    task_type: str
    system_prompt: str
    rag_context_template: Optional[str]
    use_rag: bool
    is_default: bool
    version: int
    created_at: str
    updated_at: str


class PromptService:
    """
    Service for system prompt management.

    Handles:
    - Prompt CRUD operations
    - Default prompt resolution (project → global fallback)
    - System prompt building with RAG context
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_prompts(
        self,
        project_id: Optional[str] = None,
        task_type: Optional[str] = None,
        include_global: bool = True
    ) -> list[Prompt]:
        """
        List prompts, optionally filtered by project and/or task type.

        Args:
            project_id: Filter to specific project (None = global only)
            task_type: Filter to specific task type
            include_global: Include global prompts when project_id is specified
        """
        conditions = []

        if project_id:
            if include_global:
                # Include both project-specific and global prompts
                conditions.append(
                    or_(
                        Prompt.project_id == project_id,
                        Prompt.project_id.is_(None)
                    )
                )
            else:
                conditions.append(Prompt.project_id == project_id)
        else:
            # Global prompts only
            conditions.append(Prompt.project_id.is_(None))

        if task_type:
            conditions.append(Prompt.task_type == task_type)

        stmt = select(Prompt).where(and_(*conditions)).order_by(Prompt.task_type, Prompt.name)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_prompt(self, prompt_id: str) -> Optional[Prompt]:
        """Get a specific prompt by ID."""
        stmt = select(Prompt).where(Prompt.id == prompt_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_default_prompt(
        self,
        task_type: str,
        project_id: Optional[str] = None
    ) -> Optional[Prompt]:
        """
        Get the default prompt for a task type.

        Resolution order:
        1. Project-specific default for this task_type
        2. Global default for this task_type
        3. None if no default exists
        """
        # First try project-specific default
        if project_id:
            stmt = select(Prompt).where(
                and_(
                    Prompt.project_id == project_id,
                    Prompt.task_type == task_type,
                    Prompt.is_default == True
                )
            )
            result = await self.db.execute(stmt)
            prompt = result.scalar_one_or_none()
            if prompt:
                return prompt

        # Fall back to global default
        stmt = select(Prompt).where(
            and_(
                Prompt.project_id.is_(None),
                Prompt.task_type == task_type,
                Prompt.is_default == True
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_prompt(
        self,
        name: str,
        task_type: str,
        system_prompt: str,
        project_id: Optional[str] = None,
        description: Optional[str] = None,
        rag_context_template: Optional[str] = None,
        use_rag: bool = True,
        is_default: bool = False
    ) -> Prompt:
        """Create a new prompt."""
        # Validate project exists if specified
        if project_id:
            proj_stmt = select(Project).where(Project.id == project_id)
            proj_result = await self.db.execute(proj_stmt)
            if not proj_result.scalar_one_or_none():
                raise ValueError(f"Project not found: {project_id}")

        # If setting as default, unset other defaults for same scope/task
        if is_default:
            await self._unset_defaults(project_id, task_type)

        prompt = Prompt(
            project_id=project_id,
            name=name,
            description=description,
            task_type=task_type,
            system_prompt=system_prompt,
            rag_context_template=rag_context_template,
            use_rag=use_rag,
            is_default=is_default,
            version=1
        )

        self.db.add(prompt)
        await self.db.commit()
        await self.db.refresh(prompt)

        logger.info(
            "Created prompt",
            prompt_id=prompt.id,
            name=name,
            task_type=task_type,
            project_id=project_id
        )

        return prompt

    async def update_prompt(
        self,
        prompt_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        system_prompt: Optional[str] = None,
        rag_context_template: Optional[str] = None,
        use_rag: Optional[bool] = None,
        is_default: Optional[bool] = None,
        increment_version: bool = False
    ) -> Optional[Prompt]:
        """Update an existing prompt."""
        prompt = await self.get_prompt(prompt_id)
        if not prompt:
            return None

        if name is not None:
            prompt.name = name
        if description is not None:
            prompt.description = description
        if system_prompt is not None:
            prompt.system_prompt = system_prompt
        if rag_context_template is not None:
            prompt.rag_context_template = rag_context_template
        if use_rag is not None:
            prompt.use_rag = use_rag
        if is_default is not None:
            if is_default:
                await self._unset_defaults(prompt.project_id, prompt.task_type)
            prompt.is_default = is_default
        if increment_version:
            prompt.version += 1

        await self.db.commit()
        await self.db.refresh(prompt)

        logger.info(
            "Updated prompt",
            prompt_id=prompt_id,
            version=prompt.version
        )

        return prompt

    async def delete_prompt(self, prompt_id: str) -> bool:
        """Delete a prompt. Returns True if deleted, False if not found."""
        prompt = await self.get_prompt(prompt_id)
        if not prompt:
            return False

        # Prevent deletion of seeded default prompts
        if prompt_id in ('default-knowledge-prompt', 'default-coding-prompt'):
            raise ValueError("Cannot delete built-in default prompts")

        await self.db.delete(prompt)
        await self.db.commit()

        logger.info("Deleted prompt", prompt_id=prompt_id)
        return True

    async def duplicate_prompt(
        self,
        prompt_id: str,
        new_name: str,
        target_project_id: Optional[str] = None
    ) -> Optional[Prompt]:
        """
        Duplicate an existing prompt, optionally to a different project.
        Useful for creating project-specific versions from global templates.
        """
        source = await self.get_prompt(prompt_id)
        if not source:
            return None

        return await self.create_prompt(
            name=new_name,
            task_type=source.task_type,
            system_prompt=source.system_prompt,
            project_id=target_project_id,
            description=source.description,
            rag_context_template=source.rag_context_template,
            use_rag=source.use_rag,
            is_default=False  # Duplicates are not default
        )

    async def _unset_defaults(self, project_id: Optional[str], task_type: str):
        """Unset is_default for all prompts in the same scope/task."""
        if project_id:
            stmt = select(Prompt).where(
                and_(
                    Prompt.project_id == project_id,
                    Prompt.task_type == task_type,
                    Prompt.is_default == True
                )
            )
        else:
            stmt = select(Prompt).where(
                and_(
                    Prompt.project_id.is_(None),
                    Prompt.task_type == task_type,
                    Prompt.is_default == True
                )
            )

        result = await self.db.execute(stmt)
        for prompt in result.scalars():
            prompt.is_default = False

    def build_system_prompt(
        self,
        prompt: Prompt,
        rag_context: Optional[str] = None
    ) -> str:
        """
        Build the final system prompt, optionally injecting RAG context.

        Args:
            prompt: The Prompt object to use
            rag_context: Formatted RAG context to inject (if any)

        Returns:
            The complete system prompt string
        """
        base_prompt = prompt.system_prompt

        if rag_context and prompt.use_rag:
            template = prompt.rag_context_template or DEFAULT_RAG_CONTEXT_TEMPLATE
            context_section = template.format(context=rag_context)
            return f"{base_prompt}\n\n{context_section}"

        return base_prompt

    async def get_task_types(self, project_id: Optional[str] = None) -> list[str]:
        """Get list of unique task types for prompts in scope."""
        if project_id:
            stmt = select(Prompt.task_type).where(
                or_(
                    Prompt.project_id == project_id,
                    Prompt.project_id.is_(None)
                )
            ).distinct()
        else:
            stmt = select(Prompt.task_type).where(
                Prompt.project_id.is_(None)
            ).distinct()

        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]
