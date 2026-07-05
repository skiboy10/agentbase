"""
Database connection and session management.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()

settings = get_settings()

# Convert sync URL to async URL
database_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(
    database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


async def get_db() -> AsyncSession:
    """Dependency for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database and seed default data.

    Alembic migrations are run separately before app startup.
    This function only handles seeding.
    """
    await seed_default_prompts()


async def seed_default_prompts():
    """Seed default global prompts if they don't exist."""
    # Import here to avoid circular imports
    from app.models import Prompt

    async with async_session_maker() as session:
        # Each default prompt is guarded individually so new task types
        # seed on existing installs too.
        stmt = select(Prompt).where(Prompt.id == 'default-knowledge-prompt')
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            await _seed_knowledge_prompt(session)

        stmt = select(Prompt).where(Prompt.id == 'default-question-generation-prompt')
        if not (await session.execute(stmt)).scalar_one_or_none():
            session.add(Prompt(
                id='default-question-generation-prompt',
                project_id=None,
                name='Question Generation',
                description='Drafts evaluation questions from library documents',
                task_type='question_generation',
                system_prompt=(
                    "You are building an evaluation question set for a knowledge library.\n"
                    "Given a document, draft {n} questions a real user would plausibly ask "
                    "that this document answers. For each, state the facts a good answer "
                    "must contain.\n\n"
                    'Return ONLY a JSON array: [{"question": "...", "expected_criteria": "..."}]'
                ),
                use_rag=False,
                is_default=True,
                version=1,
            ))
            await session.commit()
            logger.info("Default question-generation prompt seeded")

        stmt = select(Prompt).where(Prompt.id == 'default-answer-evaluation-prompt')
        if not (await session.execute(stmt)).scalar_one_or_none():
            session.add(Prompt(
                id='default-answer-evaluation-prompt',
                project_id=None,
                name='Answer Evaluation',
                description='LLM judge prompt for grading agent answers in scorecard runs',
                task_type='answer_evaluation',
                system_prompt=(
                    "You are an impartial evaluator grading an AI assistant's answer.\n\n"
                    "Grade on three dimensions, each 0.0-1.0:\n"
                    "- relevance: does the answer address the question asked?\n"
                    "- accuracy: are the facts correct per the expected criteria?\n"
                    "- groundedness: does the answer stick to retrievable facts (no invention)?\n\n"
                    "passed = true only if the answer satisfies the expected criteria.\n\n"
                    "Respond with ONLY a JSON object:\n"
                    '{"relevance": <0-1>, "accuracy": <0-1>, "groundedness": <0-1>, '
                    '"passed": <bool>, "rationale": "<one or two sentences>"}'
                ),
                use_rag=False,
                is_default=True,
                version=1,
            ))
            await session.commit()
            logger.info("Default answer-evaluation prompt seeded")


async def _seed_knowledge_prompt(session):
    """Seed the default knowledge prompt."""
    from app.models import Prompt

    knowledge_prompt = Prompt(
        id='default-knowledge-prompt',
        project_id=None,  # Global
        name='Knowledge Assistant',
        description='Default prompt for documentation lookup and knowledge questions',
        task_type='knowledge',
        system_prompt="""You are a knowledgeable assistant with access to a curated documentation library.

Your role is to:
- Answer questions accurately based on the available documentation
- Explain concepts clearly and thoroughly
- Provide relevant examples when helpful
- Reference specific documentation when available

Guidelines:
- Provide accurate, detailed answers based on the indexed documentation
- When you're uncertain, say so rather than making up information
- If the documentation doesn't cover a topic, acknowledge the limitation""",
        rag_context_template="""## Relevant Documentation

The following documentation excerpts may help answer the user's question:

{context}

---

Use this documentation to provide accurate, sourced answers. If the documentation doesn't cover the question, you may use your general knowledge but indicate when you're doing so.""",
        use_rag=True,
        is_default=True,
        version=1
    )

    session.add(knowledge_prompt)
    await session.commit()
    logger.info("Default knowledge prompt seeded")
