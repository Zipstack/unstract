#!/usr/bin/env python3
"""
Comprehensive Multi-Agent Workflow Example using Unstract AutoGen Client.

This example demonstrates how to create multiple AI agents using the Unstract AutoGen Client
and orchestrate them in a collaborative workflow to solve complex tasks.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, List

from autogen_core.models import SystemMessage, UserMessage
from unstract.autogen_client import UnstractAutoGenClient


@dataclass
class AgentConfig:
    """Configuration for an AI agent."""

    name: str
    role: str
    system_prompt: str
    specialty: str


class MockLLMAdapter:
    """
    Enhanced mock LLM adapter that provides different responses based on agent roles.
    In production, you would replace this with your actual Unstract SDK adapter.
    """

    def __init__(self, agent_name: str = "default"):
        self.agent_name = agent_name
        self.call_count = 0

        # Role-specific response patterns
        self.response_patterns = {
            "researcher": self._researcher_response,
            "analyst": self._analyst_response,
            "writer": self._writer_response,
            "reviewer": self._reviewer_response,
            "coordinator": self._coordinator_response,
        }

    def completion(self, messages: list, **kwargs: Any) -> Any:
        """Generate role-appropriate responses."""
        self.call_count += 1

        # Get the last user message
        last_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_message = msg.get("content", "")
                break

        # Determine response based on agent role
        role = self.agent_name.lower()
        response_func = self.response_patterns.get(role, self._default_response)
        content = response_func(last_message, messages)

        return self._create_response(content, last_message)

    def _researcher_response(self, message: str, context: list) -> str:
        """Research-focused responses."""
        if "research" in message.lower() or "find" in message.lower():
            return f"Based on my research, here are the key findings about '{message}': I've found 3 credible sources that indicate this topic has significant implications. The data suggests a 75% correlation with current market trends."
        elif "data" in message.lower():
            return "I've compiled comprehensive data from multiple sources. The statistical analysis shows strong evidence supporting the hypothesis with a confidence interval of 95%."
        else:
            return f"I'll conduct thorough research on: {message}. Let me gather information from academic sources, industry reports, and recent publications."

    def _analyst_response(self, message: str, context: list) -> str:
        """Analysis-focused responses."""
        if "analyze" in message.lower() or "analysis" in message.lower():
            return f"My analysis of '{message}' reveals: 1) Primary factors include market volatility and user behavior patterns. 2) Risk assessment indicates moderate to high impact. 3) Recommended strategy involves phased implementation."
        elif "trend" in message.lower():
            return "Trend analysis shows an upward trajectory with seasonal variations. The 12-month forecast indicates 15-20% growth potential with key inflection points in Q2 and Q4."
        else:
            return f"Analyzing the provided information: {message}. I'll examine patterns, correlations, and derive actionable insights from the data."

    def _writer_response(self, message: str, context: list) -> str:
        """Writing-focused responses."""
        if "write" in message.lower() or "draft" in message.lower():
            return f"Here's a well-structured draft addressing '{message}':\n\n## Executive Summary\nThis document presents a comprehensive overview of the topic.\n\n## Key Points\n- Strategic considerations\n- Implementation timeline\n- Expected outcomes\n\n## Conclusion\nThe analysis supports proceeding with the recommended approach."
        elif "report" in message.lower():
            return "I've prepared a professional report with clear sections, executive summary, detailed findings, and actionable recommendations. The document follows industry best practices for clarity and impact."
        else:
            return f"I'll craft compelling content for: {message}. This will include clear structure, engaging narrative, and persuasive arguments tailored to the target audience."

    def _reviewer_response(self, message: str, context: list) -> str:
        """Review-focused responses."""
        if "review" in message.lower() or "feedback" in message.lower():
            return f"Review complete for '{message}': ✅ Content quality: Excellent ✅ Accuracy: Verified ✅ Structure: Well-organized ⚠️ Suggestions: Consider adding more specific examples in section 2."
        elif "quality" in message.lower():
            return "Quality assessment: The work meets professional standards with minor improvements needed. Grammar and style are consistent. Technical accuracy is verified. Recommend final polish before delivery."
        else:
            return f"Conducting thorough review of: {message}. I'll evaluate accuracy, clarity, completeness, and provide constructive feedback for improvement."

    def _coordinator_response(self, message: str, context: list) -> str:
        """Coordination-focused responses."""
        if "coordinate" in message.lower() or "manage" in message.lower():
            return f"Coordinating workflow for '{message}': 📋 Task assignment complete ⏰ Timeline established 👥 Team synchronized 📊 Progress tracking initiated. Next milestone in 48 hours."
        elif "status" in message.lower():
            return "Project status update: Research phase 100% complete ✅ Analysis phase 80% complete 🔄 Writing phase 40% complete ⏳ Review phase pending. Overall progress: 73% on schedule."
        else:
            return f"Managing project: {message}. I'll ensure smooth coordination between team members, track deliverables, and maintain quality standards throughout the workflow."

    def _default_response(self, message: str, context: list) -> str:
        """Default response for unknown roles."""
        return f"I understand your request: '{message}'. I'll work on this task and provide you with a comprehensive response based on my capabilities."

    def _create_response(self, content: str, original_message: str) -> Any:
        """Create properly formatted response object."""

        class CompletionResponse:
            def __init__(self, content: str):
                self.choices = [Choice(content)]
                self.usage = Usage(original_message)
                self.cached = False

        class Choice:
            def __init__(self, content: str):
                self.message = Message(content)
                self.finish_reason = "stop"

        class Message:
            def __init__(self, content: str):
                self.content = content

        class Usage:
            def __init__(self, original_message: str):
                self.prompt_tokens = max(5, len(original_message.split()))
                self.completion_tokens = max(10, len(content.split()) // 2)

        return CompletionResponse(content)


class AIAgent:
    """Represents an AI agent with specific role and capabilities."""

    def __init__(self, config: AgentConfig, adapter: MockLLMAdapter):
        self.config = config
        self.client = UnstractAutoGenClient(
            llm_adapter=adapter, timeout=30.0, enable_retries=True, max_retries=2
        )
        self.conversation_history = []

    async def process_task(self, task: str, context: list[str] = None) -> str:
        """Process a task and return the response."""
        messages = [
            SystemMessage(content=self.config.system_prompt, source="system"),
        ]

        # Add context if provided
        if context:
            context_msg = f"Context from previous agents: {' | '.join(context)}"
            messages.append(SystemMessage(content=context_msg, source="system"))

        # Add the current task
        messages.append(UserMessage(content=task, source="user"))

        # Get response from the agent
        response = await self.client.create(messages)

        # Store in conversation history
        self.conversation_history.append(
            {
                "task": task,
                "response": response.content,
                "tokens_used": response.usage.prompt_tokens
                + response.usage.completion_tokens,
            }
        )

        return response.content

    async def get_usage_stats(self) -> dict:
        """Get usage statistics for this agent."""
        total_usage = self.client.total_usage()
        return {
            "agent": self.config.name,
            "total_tokens": total_usage.prompt_tokens + total_usage.completion_tokens,
            "prompt_tokens": total_usage.prompt_tokens,
            "completion_tokens": total_usage.completion_tokens,
            "conversations": len(self.conversation_history),
        }

    async def close(self):
        """Clean up the agent."""
        await self.client.close()


class MultiAgentWorkflow:
    """Orchestrates multiple AI agents in a collaborative workflow."""

    def __init__(self):
        self.agents = {}
        self.workflow_results = []

    def add_agent(self, config: AgentConfig) -> AIAgent:
        """Add an agent to the workflow."""
        adapter = MockLLMAdapter(config.name.lower())
        agent = AIAgent(config, adapter)
        self.agents[config.name] = agent
        return agent

    async def run_sequential_workflow(self, initial_task: str) -> dict:
        """Run agents in sequence, passing results between them."""
        print(f"🚀 Starting Sequential Workflow: {initial_task}")
        print("=" * 60)

        context = []
        results = {}

        # Define workflow sequence
        workflow_steps = [
            ("Researcher", f"Research the topic: {initial_task}"),
            ("Analyst", f"Analyze the research findings about: {initial_task}"),
            ("Writer", f"Write a comprehensive report about: {initial_task}"),
            (
                "Reviewer",
                f"Review and provide feedback on the report about: {initial_task}",
            ),
            ("Coordinator", f"Coordinate final delivery for: {initial_task}"),
        ]

        for step_num, (agent_name, task) in enumerate(workflow_steps, 1):
            if agent_name not in self.agents:
                print(f"⚠️ Agent '{agent_name}' not found, skipping step {step_num}")
                continue

            print(f"\n📋 Step {step_num}: {agent_name}")
            print(f"Task: {task}")
            print("-" * 40)

            agent = self.agents[agent_name]
            response = await agent.process_task(task, context)

            print(f"✅ {agent_name} Response:")
            print(f"{response[:200]}..." if len(response) > 200 else response)

            # Add response to context for next agent
            context.append(f"{agent_name}: {response[:100]}...")
            results[agent_name] = response

            # Keep context manageable (last 3 responses)
            if len(context) > 3:
                context = context[-3:]

        self.workflow_results.append(
            {
                "task": initial_task,
                "results": results,
                "timestamp": asyncio.get_event_loop().time(),
            }
        )

        return results

    async def run_parallel_analysis(self, topic: str) -> dict:
        """Run multiple agents in parallel for different perspectives."""
        print(f"\n🔄 Running Parallel Analysis: {topic}")
        print("=" * 60)

        # Define parallel tasks
        parallel_tasks = [
            ("Researcher", f"Research technical aspects of: {topic}"),
            ("Analyst", f"Analyze market implications of: {topic}"),
            ("Writer", f"Draft executive summary for: {topic}"),
        ]

        # Run tasks in parallel
        tasks = []
        for agent_name, task in parallel_tasks:
            if agent_name in self.agents:
                print(f"🔄 Starting {agent_name}: {task}")
                agent = self.agents[agent_name]
                tasks.append(agent.process_task(task))

        # Wait for all tasks to complete
        responses = await asyncio.gather(*tasks)

        # Combine results
        results = {}
        for i, (agent_name, _) in enumerate(parallel_tasks):
            if i < len(responses):
                results[agent_name] = responses[i]
                print(f"\n✅ {agent_name} completed:")
                print(
                    f"{responses[i][:150]}..."
                    if len(responses[i]) > 150
                    else responses[i]
                )

        return results

    async def get_workflow_stats(self) -> dict:
        """Get comprehensive workflow statistics."""
        stats = {"agents": {}, "workflow_summary": {}}

        total_tokens = 0
        total_conversations = 0

        for agent_name, agent in self.agents.items():
            agent_stats = await agent.get_usage_stats()
            stats["agents"][agent_name] = agent_stats
            total_tokens += agent_stats["total_tokens"]
            total_conversations += agent_stats["conversations"]

        stats["workflow_summary"] = {
            "total_agents": len(self.agents),
            "total_tokens_used": total_tokens,
            "total_conversations": total_conversations,
            "completed_workflows": len(self.workflow_results),
        }

        return stats

    async def close_all_agents(self):
        """Close all agents and clean up resources."""
        for agent in self.agents.values():
            await agent.close()
        print("🧹 All agents closed successfully")


async def main():
    """Main demonstration of the multi-agent workflow."""
    print("🤖 Unstract AutoGen Multi-Agent Workflow Demo")
    print("=" * 70)
    print(
        "This demo shows how multiple AI agents collaborate using Unstract's AutoGen client"
    )
    print()

    # Create workflow manager
    workflow = MultiAgentWorkflow()

    # Define agent configurations
    agent_configs = [
        AgentConfig(
            name="Researcher",
            role="Research Specialist",
            system_prompt="You are a thorough research specialist. You excel at gathering information from multiple sources, verifying facts, and presenting comprehensive findings. Always provide evidence-based insights.",
            specialty="Information gathering and fact verification",
        ),
        AgentConfig(
            name="Analyst",
            role="Data Analyst",
            system_prompt="You are an expert data analyst. You specialize in examining information, identifying patterns, assessing risks, and providing strategic insights. Your analysis is always data-driven and objective.",
            specialty="Pattern recognition and strategic analysis",
        ),
        AgentConfig(
            name="Writer",
            role="Content Writer",
            system_prompt="You are a professional content writer. You excel at creating clear, engaging, and well-structured documents. You adapt your writing style to the audience and purpose.",
            specialty="Clear communication and documentation",
        ),
        AgentConfig(
            name="Reviewer",
            role="Quality Reviewer",
            system_prompt="You are a meticulous quality reviewer. You examine content for accuracy, clarity, completeness, and professional standards. You provide constructive feedback for improvement.",
            specialty="Quality assurance and feedback",
        ),
        AgentConfig(
            name="Coordinator",
            role="Project Coordinator",
            system_prompt="You are an efficient project coordinator. You manage workflows, track progress, ensure deadlines are met, and facilitate communication between team members.",
            specialty="Project management and coordination",
        ),
    ]

    # Add agents to workflow
    print("👥 Initializing AI Agents:")
    for config in agent_configs:
        agent = workflow.add_agent(config)
        print(f"  ✅ {config.name} ({config.role}) - {config.specialty}")

    print(f"\n🎯 Total agents created: {len(workflow.agents)}")

    try:
        # Scenario 1: Sequential workflow for comprehensive project
        print("\n" + "=" * 70)
        print("📋 SCENARIO 1: Sequential Collaborative Workflow")
        print("=" * 70)

        sequential_results = await workflow.run_sequential_workflow(
            "Artificial Intelligence in Healthcare: Opportunities and Challenges"
        )

        # Scenario 2: Parallel analysis for multiple perspectives
        print("\n" + "=" * 70)
        print("📊 SCENARIO 2: Parallel Multi-Perspective Analysis")
        print("=" * 70)

        parallel_results = await workflow.run_parallel_analysis(
            "Cloud Computing Security Best Practices"
        )

        # Display comprehensive statistics
        print("\n" + "=" * 70)
        print("📈 WORKFLOW STATISTICS")
        print("=" * 70)

        stats = await workflow.get_workflow_stats()

        print("\n🤖 Agent Performance:")
        for agent_name, agent_stats in stats["agents"].items():
            print(f"  {agent_name}:")
            print(f"    💬 Conversations: {agent_stats['conversations']}")
            print(f"    🔤 Total tokens: {agent_stats['total_tokens']}")
            print(
                f"    📝 Avg tokens/conversation: {agent_stats['total_tokens'] // max(1, agent_stats['conversations'])}"
            )

        print("\n📊 Workflow Summary:")
        summary = stats["workflow_summary"]
        print(f"  👥 Total agents: {summary['total_agents']}")
        print(f"  💬 Total conversations: {summary['total_conversations']}")
        print(f"  🔤 Total tokens used: {summary['total_tokens_used']}")
        print(f"  ✅ Completed workflows: {summary['completed_workflows']}")

        print("\n🎉 Multi-agent workflow demonstration completed successfully!")
        print("\n💡 Key Benefits Demonstrated:")
        print("  ✅ Specialized agent roles for specific tasks")
        print("  ✅ Sequential workflows with context passing")
        print("  ✅ Parallel processing for multiple perspectives")
        print("  ✅ Comprehensive usage tracking and analytics")
        print("  ✅ Proper resource management and cleanup")

        return True

    except Exception as e:
        print(f"\n❌ Workflow failed: {e}")
        return False

    finally:
        # Always clean up resources
        await workflow.close_all_agents()


if __name__ == "__main__":
    # Run the multi-agent workflow demonstration
    success = asyncio.run(main())
    exit(0 if success else 1)
