"""Offline contract test for the real four-AgentChat sequential orchestration path.

Fake only the network/model layer, not the SupportFlow workflow.
"""
import asyncio
import json
import sys
import types
import pytest

from supportflow.ai.pipeline import call_autogen_team
from supportflow.ai.rules import validated_outcome


class TextMessage:
    def __init__(self, source, content):
        self.source = source
        self.content = content


class FakeModelClient:
    instances=[]
    def __init__(self, **kwargs):
        self.closed=False
        self.instances.append(self)
    async def close(self):
        self.closed=True


class FakeAssistantAgent:
    call_order=[]
    skip_tools=False

    def __init__(self, name, model_client, tools=None, **kwargs):
        self.name=name
        self.tools=tools or []

    async def run(self, task):
        self.call_order.append(self.name)
        if self.name=='query_agent':
            value={'category':'Refund','urgency':'High','sentiment':'Angry',
                   'summary':'Damaged blender refund request'}
        elif self.name=='knowledge_agent':
            if self.tools and not self.skip_tools:
                tool_result=await self.tools[0]('damaged blender refund')
                evidence=json.loads(tool_result)['verified_passages']
            else:
                evidence=[]
            value={'citations':[p['citation'] for p in evidence],
                   'finding':'Policy retrieved' if evidence else 'No evidence'}
        elif self.name=='resolution_agent':
            value={'reply':'We have received your request and will review it.',
                   'citations':['refund_policy.md#p1'], 'confidence':'medium',
                   'needs_human':True, 'requires_refund_or_payment_action':True}
        else:
            if self.tools and not self.skip_tools:
                await self.tools[0]('Refund','High',True,'Refund needs approval')
            value={'escalation_recommended':True,'escalation_reason':'Refund needs approval',
                   'logged':True}
        return types.SimpleNamespace(messages=[TextMessage('user',task),
                                                TextMessage(self.name,json.dumps(value))])


def install_fakes(monkeypatch):
    fake_agents=types.ModuleType('autogen_agentchat.agents')
    fake_agents.AssistantAgent=FakeAssistantAgent
    fake_openai=types.ModuleType('autogen_ext.models.openai')
    fake_openai.OpenAIChatCompletionClient=FakeModelClient
    monkeypatch.setitem(sys.modules,'autogen_agentchat',types.ModuleType('autogen_agentchat'))
    monkeypatch.setitem(sys.modules,'autogen_agentchat.agents',fake_agents)
    monkeypatch.setitem(sys.modules,'autogen_ext',types.ModuleType('autogen_ext'))
    monkeypatch.setitem(sys.modules,'autogen_ext.models',types.ModuleType('autogen_ext.models'))
    monkeypatch.setitem(sys.modules,'autogen_ext.models.openai',fake_openai)


def test_real_orchestrator_four_ordered_agents_and_tools(monkeypatch):
    install_fakes(monkeypatch)
    FakeAssistantAgent.skip_tools=False
    FakeAssistantAgent.call_order=[]
    passages=[{'citation':'refund_policy.md#p1','passage':'Refund decisions require human review'}]
    snapshot={'ticket_id':'TKT-X','title':'Damaged blender','complaint':'My blender is damaged',
              'category':'Refund','priority':'P1','order':None}
    steps=[]
    result=asyncio.run(call_autogen_team(snapshot,passages,
                                         api_key='fake',on_step=steps.append))
    expected=['query_agent','knowledge_agent','resolution_agent','log_agent']
    assert steps==expected==FakeAssistantAgent.call_order
    assert set(result.replies)==set(expected)
    assert result.all_events==8
    outcome=validated_outcome(ticket_category='Refund',ticket_priority='P1',
                               complaint=snapshot['complaint'],replies=result.replies,
                               allowed_citations=passages)
    assert outcome['sources'][0]['citation']=='refund_policy.md#p1'
    assert outcome['escalated'] is True
    assert FakeModelClient.instances[-1].closed is True


def test_missing_tool_call_is_reported_and_client_closed(monkeypatch):
    install_fakes(monkeypatch)
    FakeAssistantAgent.skip_tools=True
    snapshot={'ticket_id':'TKT-X','title':'Refund','complaint':'Refund please',
              'category':'Refund','priority':'P1','order':None}
    try:
        with pytest.raises(RuntimeError,match='knowledge_agent did not invoke'):
            asyncio.run(call_autogen_team(snapshot,[],api_key='fake'))
        assert FakeModelClient.instances[-1].closed is True
    finally:
        FakeAssistantAgent.skip_tools=False
