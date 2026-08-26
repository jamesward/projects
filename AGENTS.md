# James Ward Projects

I maintain numerous libraries, websites, build plugins, code samples, IaC tooling, and Nix Packages.
Consistency helps reduce the maintaince burden.

## General Guidelines
- Use dependabot to keep dependencies up-to-date
- Use build-defined agent skills and project level MCPs
- CI should always exist for maintained projects
- CI should generally run on push to the default branch and on PRs
- CI should have single concurrency for `${{ github.workflow }}-${{ github.ref }}` and `cancel-in-progress`
- Testcontainers should be used for service dependencies in local dev & test


## Library Guidelines
- Must have a javadocs.dev badge


## Website Guidelines


## Build Plugin Guidelines


## Code Sample Guidelines
- CI should validate compilation



Daily routines





## Maintained Projects

### Agent Integration Demo

Source: https://github.com/jamesward/agent-integration-demo


### ai4jvm.com

Source: https://github.com/jamesward/ai4jvm
AWS Infra: https://github.com/jamesward/domains


### Bootiful Spring AI Book & MCP

In progress book with Josh Long about Spring AI. MCP server for the book with IDP.

#### mcp.bootifulspringai.com

Source: https://github.com/agentic-spring-ai-book/mcp-server
Heroku App: spring-ai-mcp

#### login.bootifulspringai.com

Source: https://github.com/agentic-spring-ai-book/login-server
Heroku App: spring-ai-login


### cfn-extras-resource

CloudFormation Extras Resource

Source: https://github.com/jamesward/cfn-extras-resource
S3 Bucket: s3://cfn-extras-resource


### cimd.now

Enable CIMD testing

Source: https://github.com/jamesward/cimdapp
Heroku App: cimdapp


### CloudFormation Pkl Extras

Source: https://github.com/jamesward/cfn-pkl-extras


### EasyRacer

Examples of structured concurrency

Source: https://github.com/jamesward/easyracer
Container: ghcr.io/jamesward/easyracer:latest


### Effect Oriented Programming Book & MCP

Book & MCP about Effect Oriented Programming

#### login.effectorientedprogramming.com

Source: https://github.com/EffectOrientedProgramming/login
Heroku App: eop-login

#### mcp.effectorientedprogramming.com

Source: https://github.com/EffectOrientedProgramming/mcp
Heroku App: eop-mcp


### Happy Path Programming

Source: https://github.com/MindviewLLC/podcast
AWS Infra: https://github.com/jamesward/domains


### hello-spring-ai-agentcore

Source: https://github.com/jamesward/hello-spring-ai-agentcore


### hello-spring-ai-bedrock

Minimal Spring AI Bedrock example

Source: https://github.com/jamesward/hello-spring-ai-bedrock


### hello-zio-http

Small sample of ZIO HTTP

Source: https://github.com/jamesward/hello-zio-http


### Heroku Buildpack Scala

Source: https://github.com/jamesward/buildpack-scala


### Heroku Buildpack Scala Native

Source: https://github.com/jamesward/buildpack-scala-native


### James Ward Agent Skills

Source: https://github.com/jamesward/skills
Maven Central: com.jamesward:skills


### James Ward Domains & Websites

Pkl CloudFormation IaC for domains & websites on AWS

Source: https://github.com/jamesward/domains


### jamesward.com

Source: https://github.com/jamesward/jamesward
AWS Infra: https://github.com/jamesward/domains


### javadocs.dev

Website & MCP for Java/Kotlin/Scala docs

Source: https://github.com/jamesward/javadoccentral
Heroku App: javadocs


### json-paste.herokuapp.com

Source: https://github.com/jamesward/json-paste
Heroku App: json-paste


### Leanpub GitHub Actions

Source: https://github.com/jamesward/pklgha


### login.jamesward.dev

Demo IDP

Source: https://github.com/jamesward/login-jamesward-dev
Heroku App: login-jamesward-dev


### mcp-demo.jamesward.com

Source: https://github.com/jamesward/mcp-apps-demo
Heroku App: mcp-apps-demo


### mcp-test.jamesward.com

Source: https://github.com/jamesward/hello-spring-mcp-server
Heroku App: mcp-sample


### mytoolbook.ai

ToolBooks

Source: https://github.com/EffectOrientedProgramming/toolbook
Heroku Apps:
- mytoolbook-api (private via API PSK) api.mytoolbook.ai
- mytoolbook-login login.mytoolbook.ai
- mytoolbook-mcp mcp.mytoolbook.ai
- mytoolbook-proxy proxy.mytoolbook.ai
- mytoolbook-www www.mytoolbook.ai


### Pkl GitHub Actions

Source: https://github.com/jamesward/pklgha


### sbt-mcp

Source: https://github.com/jamesward/sbt-mcp
Maven Central: com.jamesward:sbt-mcp2_3


### sbt-reload

Source: https://github.com/jamesward/sbt-reload
Maven Central: com.jamesward:sbt-reload_sbt2_3


### sbt-sass

Source: https://github.com/jamesward/sbt-sass
Maven Central: com.jamesward:sbt-sass2_3


### SkillsJars

Agent Skills in JARs

#### www.skillsjars.com

Source: https://github.com/skillsjars/skillsjars
Heroku App: skillsjars

#### SkillsJars Gradle Plugin

https://github.com/skillsjars/skillsjars-gradle-plugin

#### SkillsJars Maven Plugin

https://github.com/skillsjars/skillsjars-maven-plugin

#### SkillsJars sbt Plugin

https://github.com/skillsjars/skillsjars-sbt-plugin

#### SkillsJars Spring Example

https://github.com/skillsjars/skillsjars-example-spring-ai


### Spring AI MCP Demo

Source: https://github.com/jamesward/spring-ai-mcp-demo


### WebJars

#### webjars.org

Search & Deploy WebJars

Source: https://github.com/webjars/webjars
Heroku App: webjars

#### WebJars CDN

Serves https://www.jsdelivr.com/ WebJar Contents

Source: https://github.com/webjars/webjars-file-service
Heroku App: webjars-file-service

#### Classic WebJars Builds

Old Classic WebJars each had a GitHub repo in: https://github.com/webjars
The new Classic WebJars have metadata in: https://github.com/webjars/webjars-classic

#### Legacy WebJars Locator

https://github.com/webjars/webjars-locator
https://github.com/webjars/webjars-locator-core

#### Lite WebJars Locator

https://github.com/webjars/webjars-locator-lite

#### WebJars sbt Plugin

https://github.com/webjars/sbt-webjars


### zio-bedrock-converse

ZIO Bedrock Converse Library

Source: https://github.com/jamesward/zio-bedrock-converse
Maven Central: com.jamesward:zio-bedrock-converse_3

#### Hello ZIO Bedrock

Source: https://github.com/jamesward/hello-zio-bedrock


### zio-evals

ZIO Agent Evals Library

Source: https://github.com/jamesward/zio-evals
Maven Central: com.jamesward:zio-evals_3


### zio-git

Minimal ZIO Git Library

Source: https://github.com/jamesward/zio-git
Maven Central: com.jamesward:zio-git


### zio-http-guard

Abuse protection middleware for ZIO HTTP

Source: https://github.com/jamesward/zio-http-guard
Maven Central: com.jamesward:zio-http-guard_3


### zio-http-mcp

ZIO HTTP MCP library

Source: https://github.com/jamesward/zio-http-mcp
Maven Central: com.jamesward:zio-http-mcp_3

#### hello-zio-mcp

Small sample of ZIO HTTP MCP

Source: https://github.com/jamesward/hello-zio-mcp


### zio-mavencentral

Read & deploy to Maven Central

Source: https://github.com/jamesward/zio-mavencentral
Maven Central: com.jamesward:zio-mavencentral_3
