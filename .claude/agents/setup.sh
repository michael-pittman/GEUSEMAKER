#!/bin/bash

# Geuse Chat Subagent System Setup Script
# This script helps manage the Claude Code subagent system for the 3D glassmorphic chat interface

echo "🎭 Geuse Chat Subagent System Setup"
echo "======================================"

# Check if we're in the right directory
if [ ! -f "package.json" ] || [ ! -d "src" ]; then
    echo "❌ Error: Please run this script from the Geuse Chat project root directory"
    exit 1
fi

# Verify agents directory exists
if [ ! -d ".claude/agents" ]; then
    echo "❌ Error: .claude/agents directory not found"
    echo "   Please ensure the subagent system is properly installed"
    exit 1
fi

echo "✅ Found Geuse Chat project structure"
echo "✅ Found subagent system in .claude/agents"
echo ""

# Count and list agents
agent_count=$(ls -1 .claude/agents/*.md 2>/dev/null | wc -l)
echo "📊 Subagent System Status:"
echo "   Total Agents: $agent_count"
echo ""

echo "🤖 Available Specialized Agents:"
echo "================================"

# List all agents with descriptions
for agent_file in .claude/agents/*.md; do
    if [ -f "$agent_file" ]; then
        agent_name=$(basename "$agent_file" .md)
        # Extract description from the agent file
        description=$(grep "description:" "$agent_file" | sed 's/description: //' | sed 's/"//g')
        echo "• $agent_name"
        echo "  $description"
        echo ""
    fi
done

echo "🔗 Agent Chaining Examples:"
echo "=========================="
echo ""
echo "Feature Development Chain:"
echo "  geuse-orchestration-manager → glass-ux-architect → threejs-visualization-master → playwright-testing-virtuoso"
echo ""
echo "Performance Optimization:"
echo "  performance-optimization-engine → threejs-visualization-master → playwright-testing-virtuoso"
echo ""
echo "Deployment Pipeline:"
echo "  playwright-testing-virtuoso → aws-deployment-architect → n8n-automation-specialist"
echo ""
echo "Accessibility Compliance:"
echo "  theme-accessibility-guardian → glass-ux-architect → playwright-testing-virtuoso"
echo ""

echo "🚀 Quick Start Commands:"
echo "======================="
echo ""
echo "To use the orchestration manager for complex tasks:"
echo "  > Use the geuse-orchestration-manager to implement a new glassmorphic chat feature"
echo ""
echo "To optimize performance:"
echo "  > Use the performance-optimization-engine to improve 3D scene frame rates"
echo ""
echo "To test the interface:"
echo "  > Use the playwright-testing-virtuoso to validate glass effects and accessibility"
echo ""
echo "To deploy changes:"
echo "  > Use the aws-deployment-architect to deploy the latest build to production"
echo ""

echo "📚 Documentation:"
echo "================="
echo "• Agent Chains Guide: .claude/agents/AGENT_CHAINS.md"
echo "• Individual agent files: .claude/agents/*.md"
echo "• Project documentation: README.md, CLAUDE.md"
echo ""

echo "⚡ Advanced Features:"
echo "==================="
echo "• Dynamic agent selection based on task complexity"
echo "• Intelligent chaining with error recovery"
echo "• MCP Playwright integration for testing"
echo "• Real-time performance monitoring"
echo "• WCAG 2.2 accessibility compliance"
echo "• iOS 26 liquid glass aesthetic implementation"
echo ""

echo "✨ The Geuse Chat subagent system is ready!"
echo "   Start by invoking the geuse-orchestration-manager for complex workflows"
echo "   or use specific agents for targeted tasks."
