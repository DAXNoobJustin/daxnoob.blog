---
title: "MCP Server: DAX Performance Tuner"
description: "With all of the buzz around MCP servers, I wanted to see if one could be created that would help you optimize DAX. Introducing - DAX Performance Tuner!"
date:
  created: 2025-10-21
categories:
  - DAX
tags:
  - Performance
  - MCP
  - Open Source
  - Python
authors:
  - justinmartin
slug: mcp-server-dax-performance-tuner
---

**With all of the buzz around MCP servers, I wanted to see if one could be created that would help you optimize DAX. Introducing - DAX Performance Tuner**!

The MCP server give LLMs the tools it needs to optimize your DAX queries using a systematic, research-driven process.

**How it works:** After the LLM connects to your model, it prepares your query for optimization. This includes defining model measures and UDFs, executing the query several times under a trace, returning relevant optimization guidance, and defining the relevant parts of the model's metadata. After analyzing the results, the LLM will attempt to optimize your query, ensuring it returns the same results.

**Main features:**

- **Smart Discovery**: Auto-detects Power BI Desktop instances running on your machine or discovers datasets in Power BI Service workspaces
- **Deep Performance Analysis**: Captures detailed server timings including Formula Engine vs Storage Engine breakdown, high level statistics, and event-level traces to identify specific bottlenecks
- **Research Integration**: Returns targeted DAX optimization articles based on patterns detected in your query
- **Semantic Validation**: Optimization attempts are validated to ensure they return identical results to the baseline: comparing row counts, column counts, and sample records
- **Session State Management**: Tracks your baseline and optimization attempts so the LLM doesn't get lost in the process

Here is a link to the repo in Fabric Toolbox: [fabric-toolbox/tools/DAXPerformanceTunerMCPServer at main · microsoft/fabric-toolbox](https://github.com/microsoft/fabric-toolbox/tree/main/tools/DAXPerformanceTunerMCPServer)

Watch the video below to see it in action:

<div class="video-wrapper">
  <iframe src="https://www.youtube.com/embed/7CI0oShxGkU" frameborder="0" allowfullscreen></iframe>
</div>
