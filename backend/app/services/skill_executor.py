"""
Skill Executor Service

Standalone utility for executing builtin skills (calculator, time, etc.).
Extension and database tracking removed.
"""

import logging
import ast
import operator
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SkillResult:
    """Result of skill execution."""
    success: bool
    outputs: Optional[dict] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


# Safe math operators for calculator
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval_math(expr: str) -> float:
    """Safely evaluate a mathematical expression using AST parsing."""
    def _eval(node):
        if isinstance(node, ast.Num):  # Python 3.7
            return node.n
        elif isinstance(node, ast.Constant):  # Python 3.8+
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant: {node.value}")
        elif isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            op = SAFE_OPERATORS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return op(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            op = SAFE_OPERATORS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return op(operand)
        elif isinstance(node, ast.Expression):
            return _eval(node.body)
        else:
            raise ValueError(f"Unsupported expression type: {type(node).__name__}")

    tree = ast.parse(expr, mode='eval')
    return _eval(tree)


class SkillExecutor:
    """Standalone skill executor for builtin skills."""

    async def execute_skill(
        self,
        skill_id: str,
        inputs: dict,
        agent_id: Optional[str] = None,
        project_id: Optional[str] = None,
        timeout_override: Optional[int] = None
    ) -> SkillResult:
        """Execute a builtin skill by its skill_id."""
        start_time = datetime.utcnow()

        try:
            outputs = await self._execute_builtin(skill_id, inputs)
            end_time = datetime.utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            return SkillResult(
                success=True,
                outputs=outputs,
                duration_ms=duration_ms
            )

        except Exception as e:
            logger.exception(f"Skill execution failed: {skill_id}")
            return SkillResult(
                success=False,
                error=str(e),
            )

    async def _execute_builtin(self, skill_id: str, inputs: dict) -> dict:
        """Execute a builtin skill."""
        if skill_id == 'builtin.web_search':
            return await self._builtin_web_search(inputs)
        elif skill_id == 'builtin.calculator':
            return await self._builtin_calculator(inputs)
        elif skill_id == 'builtin.current_time':
            return await self._builtin_current_time(inputs)
        elif skill_id == 'builtin.url_fetch':
            return await self._builtin_url_fetch(inputs)
        else:
            raise ValueError(f"Unknown builtin skill: {skill_id}")

    async def _builtin_web_search(self, inputs: dict) -> dict:
        """Web search builtin skill (placeholder)."""
        query = inputs.get('query', '')
        return {
            'results': [],
            'message': f'Web search for "{query}" - implementation pending'
        }

    async def _builtin_calculator(self, inputs: dict) -> dict:
        """Calculator builtin skill using safe AST-based evaluation."""
        expression = inputs.get('expression', '')
        try:
            result = safe_eval_math(expression)
            return {'result': result, 'expression': expression}
        except Exception as e:
            return {'error': str(e), 'expression': expression}

    async def _builtin_current_time(self, inputs: dict) -> dict:
        """Current time builtin skill."""
        now = datetime.utcnow()
        return {
            'utc': now.isoformat(),
            'formatted': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'timestamp': int(now.timestamp())
        }

    async def _builtin_url_fetch(self, inputs: dict) -> dict:
        """URL fetch builtin skill (placeholder)."""
        url = inputs.get('url', '')
        return {
            'url': url,
            'content': '',
            'message': 'URL fetch - implementation pending'
        }
