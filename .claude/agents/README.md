# Geuse Chat Subagent System

## Overview

This directory contains a comprehensive subagent system for the Geuse Chat 3D glassmorphic interface, implementing iOS 26 liquid glass aesthetics with advanced agent chaining and dynamic selection capabilities.

## Agent Architecture

### 🎭 Master Orchestrator
- **geuse-orchestration-manager** - Intelligent workflow coordination and agent chaining

### 🎨 Design & UX Specialists  
- **glass-ux-architect** - iOS 26 liquid glass design and glassmorphic interfaces
- **theme-accessibility-guardian** - WCAG compliance and inclusive design

### 🎮 Technical Specialists
- **threejs-visualization-master** - 3D visualization and WebGL optimization
- **performance-optimization-engine** - Real-time monitoring and adaptive quality
- **playwright-testing-virtuoso** - Advanced testing with MCP integration

### 🚀 Infrastructure Specialists
- **aws-deployment-architect** - S3/CloudFront deployment and optimization
- **n8n-automation-specialist** - Workflow automation and webhook integration

## Quick Start

1. **Run the setup script**:
   ```bash
   chmod +x .claude/agents/setup.sh
   ./.claude/agents/setup.sh
   ```

2. **Start with the orchestrator for complex tasks**:
   ```
   > Use the geuse-orchestration-manager to implement a new glassmorphic feature
   ```

3. **Or invoke specific agents for targeted work**:
   ```
   > Use the glass-ux-architect to enhance the chat bubble glass effects
   > Use the performance-optimization-engine to improve mobile frame rates
   > Use the playwright-testing-virtuoso to test the new glass components
   ```

## Agent Chaining Examples

### Feature Development
```
glass-ux-architect → threejs-visualization-master → playwright-testing-virtuoso → 
theme-accessibility-guardian → performance-optimization-engine → aws-deployment-architect
```

### Performance Optimization
```
performance-optimization-engine → (threejs-visualization-master OR glass-ux-architect) → 
playwright-testing-virtuoso → aws-deployment-architect
```

### Deployment Pipeline
```
playwright-testing-virtuoso → performance-optimization-engine → aws-deployment-architect → 
n8n-automation-specialist → monitoring-validation
```

## Key Features

- **🔗 Intelligent Chaining**: Context-aware agent selection and workflow orchestration
- **⚡ MCP Integration**: Full Playwright MCP support for testing and automation
- **🎨 iOS 26 Aesthetics**: Cutting-edge liquid glass design implementation
- **📱 Cross-Platform**: Optimized for mobile, tablet, and desktop
- **♿ Accessibility**: WCAG 2.2 compliance with inclusive design patterns
- **🚀 Performance**: 60fps desktop, 30fps mobile with adaptive quality
- **☁️ Cloud-Ready**: AWS S3/CloudFront deployment with n8n automation

## Documentation

- **[AGENT_CHAINS.md](./AGENT_CHAINS.md)** - Comprehensive chaining guide
- **Individual Agent Files** - Detailed specifications for each agent
- **[../CLAUDE.md](../CLAUDE.md)** - Project overview and development guide
- **[../README.md](../README.md)** - Geuse Chat application documentation

## Agent Tool Access

All agents have access to:
- **Read, Write, Bash, Grep, Glob** - File system operations
- **Playwright MCP** - Browser automation and testing (where applicable)
- **AWS CLI** - Cloud deployment and management (where applicable)
- **Performance APIs** - Monitoring and optimization tools (where applicable)

## Best Practices

1. **Start with the orchestrator** for complex, multi-step workflows
2. **Use specific agents** for targeted tasks within their expertise
3. **Chain agents** for comprehensive feature development
4. **Validate with testing** before deployment
5. **Monitor performance** throughout the development process

The subagent system is designed to handle the complexity of modern 3D glassmorphic web applications while maintaining high performance, accessibility, and user experience standards.
