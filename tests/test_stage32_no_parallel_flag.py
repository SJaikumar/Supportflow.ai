"""Regression: don't send parallel_tool_calls when the first agent has no tools."""
import asyncio
import sys
import types

from supportflow.ai.pipeline import call_autogen_team
from test_stage31_orchestration import FakeAssistantAgent, install_fakes


def test_client_omits_parallel_tool_calls_for_toolless_agents(monkeypatch):
    install_fakes(monkeypatch)
    import autogen_ext.models.openai as fake_openai

    class ValidatingClient:
        instances = []
        def __init__(self, **kwargs):
            # OpenAI rejects parallel_tool_calls without tools; our shared
            # client must not inject it into calls for query/resolution agents.
            assert 'parallel_tool_calls' not in kwargs
            self.kwargs = kwargs
            self.closed = False
            self.instances.append(self)
        async def close(self):
            self.closed = True

    fake_openai.OpenAIChatCompletionClient = ValidatingClient
    FakeAssistantAgent.call_order = []
    FakeAssistantAgent.skip_tools = False
    snapshot = {'ticket_id': 'TKT-1', 'title': 'Damaged blender',
                'complaint': 'My blender arrived damaged',
                'category': 'Refund', 'priority': 'P1', 'order': None}
    passages = [{'citation':'refund_policy.md#p1',
                 'passage':'Refunds are subject to human approval.'}]
    result = asyncio.run(call_autogen_team(snapshot, passages, api_key='test'))
    assert set(result.replies) == {'query_agent', 'knowledge_agent',
                                   'resolution_agent', 'log_agent'}
    assert ValidatingClient.instances[0].closed
