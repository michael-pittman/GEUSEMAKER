# Geuse Chat Subagent System - Agent Chaining Guide

## Overview

The Geuse Chat subagent system implements sophisticated agent chaining for the 3D glassmorphic chat interface. Each agent is specialized for specific tasks while working together through intelligent orchestration patterns.

## Agent Chain Patterns

### 1. Feature Development Chain
**Primary Workflow**: New feature implementation with full validation
```
User Request → geuse-orchestration-manager → glass-ux-architect → threejs-visualization-master → 
playwright-testing-virtuoso → theme-accessibility-guardian → performance-optimization-engine → 
aws-deployment-architect → Completion Report
```

**Use Cases:**
- New glassmorphic UI components
- 3D scene enhancements
- Chat interface improvements
- Theme system updates

### 2. Performance Optimization Chain
**Primary Workflow**: Performance issue resolution and optimization
```
Performance Alert → geuse-orchestration-manager → performance-optimization-engine → 
(threejs-visualization-master OR glass-ux-architect) → playwright-testing-virtuoso → 
aws-deployment-architect → Monitoring Validation
```

**Use Cases:**
- FPS drops or stuttering
- Memory leaks
- Slow loading times
- Mobile performance issues

### 3. Bug Fix Chain
**Primary Workflow**: Issue resolution with targeted specialist involvement
```
Bug Report → geuse-orchestration-manager → [Appropriate Specialist] → playwright-testing-virtuoso → 
theme-accessibility-guardian → performance-optimization-engine → aws-deployment-architect
```

**Specialist Selection:**
- Glass UI bugs → glass-ux-architect
- 3D rendering issues → threejs-visualization-master
- Accessibility problems → theme-accessibility-guardian
- Deployment issues → aws-deployment-architect
- Webhook problems → n8n-automation-specialist

### 4. Deployment Chain
**Primary Workflow**: Production deployment with comprehensive validation
```
Deployment Request → geuse-orchestration-manager → playwright-testing-virtuoso → 
performance-optimization-engine → aws-deployment-architect → n8n-automation-specialist → 
Monitoring & Validation
```

**Use Cases:**
- Production deployments
- Staging environment updates
- Webhook configuration changes
- Infrastructure updates

### 5. Accessibility Compliance Chain
**Primary Workflow**: WCAG compliance validation and improvement
```
Accessibility Review → geuse-orchestration-manager → theme-accessibility-guardian → 
glass-ux-architect → playwright-testing-virtuoso → performance-optimization-engine → 
Documentation Update
```

**Use Cases:**
- WCAG 2.2 compliance audits
- Screen reader compatibility
- Keyboard navigation improvements
- High contrast mode implementation

## Agent Coordination Protocols

### Sequential Chains
**When to Use**: Linear workflows with dependencies
**Examples**: Feature development, compliance validation, deployment pipelines

**Pattern**:
```
Agent A completes → Handoff to Agent B → Agent B completes → Handoff to Agent C
```

### Parallel Chains
**When to Use**: Independent tasks that can be processed simultaneously
**Examples**: Multi-component optimization, parallel testing scenarios

**Pattern**:
```
Orchestrator splits work → [Agent A + Agent B + Agent C] execute in parallel → 
Results aggregation → Next chain step
```

### Hybrid Chains
**When to Use**: Complex workflows requiring both sequential and parallel processing
**Examples**: Large feature development, comprehensive performance optimization

**Pattern**:
```
Sequential Phase 1 → Parallel Phase 2 [A+B+C] → Sequential Phase 3 → 
Parallel Validation [D+E] → Final Sequential Phase
```

## Dynamic Agent Selection

### Context-Aware Routing
The `geuse-orchestration-manager` uses intelligent routing based on:

1. **Task Complexity Analysis**
   - Simple tasks: Single agent
   - Complex tasks: Multi-agent chains
   - Critical tasks: Full validation chains

2. **Performance Metrics**
   - Agent success rates
   - Historical performance data
   - Current system load

3. **Priority Matrix**
   ```
   Critical Path: Performance → Accessibility → Testing → Deployment
   Development: Glass Design → 3D Visualization → Integration → Testing
   Automation: n8n Workflows → AWS Deployment → Monitoring
   Quality: Testing → Accessibility → Performance → Documentation
   ```

### Agent Capability Matching
Each agent has defined capabilities that the orchestrator matches to task requirements:

- **Glass UI needs** → glass-ux-architect
- **3D/WebGL tasks** → threejs-visualization-master  
- **Testing requirements** → playwright-testing-virtuoso
- **Performance issues** → performance-optimization-engine
- **Accessibility concerns** → theme-accessibility-guardian
- **Deployment tasks** → aws-deployment-architect
- **Workflow automation** → n8n-automation-specialist

## Handoff Protocols

### Standard Handoff Pattern
```yaml
Current Agent:
  1. Complete assigned task
  2. Generate handoff report with:
     - Task completion status
     - Relevant context for next agent
     - Specific requirements or constraints
     - Performance metrics or quality checks
  3. Signal orchestrator for next agent selection

Orchestrator:
  1. Validate completion criteria
  2. Select next agent based on handoff requirements
  3. Provide context and task specification to next agent
  4. Monitor execution and handle errors

Next Agent:
  1. Receive context from previous agent
  2. Validate prerequisites are met
  3. Execute assigned tasks
  4. Prepare for next handoff or completion
```

### Error Handling in Chains
1. **Agent Failure**: Orchestrator retries or selects alternative agent
2. **Quality Gate Failure**: Chain reverses to previous agent for fixes
3. **Critical Error**: Chain halts with human escalation
4. **Timeout**: Graceful degradation with partial completion reporting

## Agent Communication Standards

### MCP Integration
All agents leverage MCP (Model Context Protocol) tools:
- **Playwright MCP**: Browser automation and testing
- **Performance MCP**: Real-time monitoring and optimization
- **AWS MCP**: Cloud infrastructure management
- **Accessibility MCP**: WCAG compliance validation

### Shared Context Management
- **Immutable logs**: All agent actions logged for audit trail
- **State synchronization**: Shared context across agent boundaries
- **Version control**: Track changes through agent chain execution
- **Rollback capability**: Revert to previous stable state if needed

## Performance Metrics

### Chain Execution Metrics
- **Average Chain Completion Time**: Target <300 seconds for complex chains
- **Agent Success Rate**: Target >95% individual agent success
- **Chain Success Rate**: Target >90% end-to-end chain completion
- **Error Recovery Time**: Target <60 seconds for automatic recovery

### Quality Metrics
- **Code Quality**: Maintain high standards through testing chains
- **Performance Targets**: 60fps desktop, 30fps mobile minimum
- **Accessibility Compliance**: 100% WCAG 2.2 AA compliance
- **Deployment Success**: 99%+ successful deployment rate

## Best Practices

### Chain Design
1. **Start Simple**: Begin with single agents, add complexity as needed
2. **Define Clear Handoffs**: Each agent should have clear success criteria
3. **Implement Quality Gates**: Validate output before proceeding to next agent
4. **Plan for Failures**: Include error handling and recovery strategies

### Agent Coordination
1. **Maintain Context**: Preserve important information across handoffs
2. **Validate Prerequisites**: Ensure each agent has what it needs to succeed
3. **Monitor Performance**: Track chain execution and optimize bottlenecks
4. **Document Decisions**: Maintain audit trail for troubleshooting

### Optimization Strategies
1. **Parallel Where Possible**: Use concurrent execution for independent tasks
2. **Cache Results**: Avoid redundant work across similar chains
3. **Optimize Handoffs**: Minimize context transfer overhead
4. **Learn from History**: Use past performance to improve routing decisions

This comprehensive agent chaining system ensures efficient, reliable, and high-quality development workflows for the Geuse Chat 3D glassmorphic interface.
