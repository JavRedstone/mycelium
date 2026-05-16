# Google Cloud Rapid Agent Hackathon 2026

**Timeline:** May 5, 2026 - June 11, 2026  
**Submission Deadline:** June 11, 2026, 2:00 P.M. PT  
**Judging:** June 22 - July 6, 2026  
**Official Site:** https://rapid-agent.devpost.com/

---

## The Challenge

Build a functional agent powered by Gemini that solves a real-world problem targeting your work, personal life, hobbies, or daily routines. Your agent must:

- **Go beyond chat** - Use tools and capabilities to actually accomplish tasks (not just answer questions)
- **Handle complexity** - Plan multi-step solutions and use available tools while keeping you in control
- **Integrate a partner** - Demonstrate meaningful integration with at least one partner's MCP server

---

## Partner Tracks

Choose **at least one** and build with their Model Context Protocol (MCP) server:

- [Arize](https://rapid-agent.devpost.com/details/arize-resources)
- [Dynatrace](https://rapid-agent.devpost.com/details/dynatrace-resources) *(new)*
- [Elastic](https://rapid-agent.devpost.com/details/elastic-resources)
- [Fivetran](https://rapid-agent.devpost.com/details/fivetran-resources)
- [GitLab](https://rapid-agent.devpost.com/details/gitlab-resources)
- [MongoDB](https://rapid-agent.devpost.com/details/mongodb-resources)

**Mycelium track strategy:** Enter **both GitLab and MongoDB tracks**. The act agent connects to both official MCP servers simultaneously — GitLab MCP (HTTP) for write actions and MongoDB MCP (stdio) for live knowledge graph queries. This is meaningful dual integration, not a token mention. The other four partners (Arize, Elastic, Fivetran, Dynatrace) are out of scope for this use case.

---

## Partner Details

### GitLab

> A complete DevSecOps platform delivered as a single application. Fundamentally changes how Dev, Sec, and Ops teams collaborate.

**Trial:** 30-day Ultimate trial — no access codes required. Includes Duo Agent Platform with **24 credits/user**.

| Feature | Status | Relevant to Mycelium? |
|---|---|---|
| **MCP Server** | Beta | **Yes — act_agent.py connects to `https://gitlab.com/api/v4/mcp` via HTTP/streamable-HTTP transport (mcp >= 1.27). Auth: `Authorization: Bearer <GITLAB_TOKEN>`.** |
| **Webhooks → Mycelium** | N/A (GitLab feature) | **Yes — event-driven pipeline triggers on push/MR/pipeline events. Requires public URL.** |
| Custom Flows | Beta | Only useful post-Cloud Run. Once deployed: trigger on MR ready → call `/graph` → post reviewer comment. |
| Custom Agents | GA | Conversational interface ("who owns X?") — requires Mycelium public URL. Lower priority. |

**Resources:**
- MCP Server: https://docs.gitlab.com/user/gitlab_duo/model_context_protocol/mcp_server/
- Custom Flows: https://docs.gitlab.com/user/duo_agent_platform/flows/custom/
- Start a Trial: https://about.gitlab.com/free-trial/

**How it applies to Mycelium:**
`act_agent.py` connects to the official GitLab MCP server at `{GITLAB_URL}/api/v4/mcp` using `streamablehttp_client` from `mcp` v1.27+. Auth via `Authorization: Bearer {GITLAB_TOKEN}`. Write-capable tools are dynamically discovered; Gemini selects which to invoke based on the risk assessment.

---

### MongoDB

> Atlas is the unified operational foundation and persistent memory layer for modern AI and agentic workloads. Combines operational, vector, and semantic data on a single platform.

**Resources:**
- Sample Mflix Dataset (includes pre-built vector embeddings): `sample_mflix.embedded_movies`
- [Data Modelling in MongoDB](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB MCP Server](https://www.mongodb.com/docs/mcp-server/)
- [MongoDB Atlas Search](https://www.mongodb.com/docs/atlas/atlas-search/)
- [MongoDB Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/)
- [Voyage AI (embeddings)](https://docs.voyageai.com/)
- [AI Learning Hub](https://www.mongodb.com/developer/products/atlas/ai-learning-hub/)

**How it applies to Mycelium:**

MongoDB Atlas is Mycelium's knowledge graph store (Motor async client, four collections: `developers`, `modules`, `tasks`, `contributions`).

**Implemented:**
- **MongoDB MCP Server** (`@mongodb-js/mongodb-mcp-server`) — `act_agent.py` connects via stdio (`npx`) and gives Gemini direct `find`/`aggregate` access to all graph collections during the execute stage. This lets the agent self-query the live graph rather than relying on the pre-built `snapshot()` context dump. Auth via `MDB_MCP_CONNECTION_STRING` env var (set to `MONGODB_URI`).

**Potential future upgrade:**
- **Vector Search on `DeveloperNode`** — embed developer expertise profiles, use Atlas Vector Search to find "who is most similar to this departing developer?" for handoff recommendations. Replaces score-based lookup with semantic similarity.

---

## Building Your Project

### Phase 1: Core Frameworks & Environment
- **Managed Setup:** Gemini Enterprise Agent Platform API Setup
- **Low-Code Path:** Agent Builder Guide
- **Developer SDK:** Gemini Enterprise Agent Platform SDK for Python
- **Get Credits:** Apply for $100 in Google Cloud credits by June 4th, 2026

### Phase 2: Action Mechanisms & Data Connectivity
- Agent Builder Extensions for external APIs
- Agent Builder Data Stores for indexing PDFs, websites, or BigQuery tables

### Phase 3: Partner Integration & Infrastructure
- Access partner-specific resources at https://rapid-agent.devpost.com/resources

### Phase 4: Reasoning, State, & Logic Hosting
- Agent Runtime for deploying Python-based agents
- Secret Manager for storing API keys

### Phase 5: Deployment & Safety
- Agent Builder Deployment for web/API access
- Cloud Run Quickstart for custom backends

---

## What to Submit

1. **Hosted project URL** - Must be functional and testable
2. **Public code repository** - Include open-source license file (visible at repo top)
3. **Demo video** - 3 minutes max, on YouTube or Vimeo, showing it working
4. **Track selection** - Which partner track you're entering
5. **Description** - Features, technologies, data sources, learnings
6. **Devpost submission form** - All required fields completed

### Project Requirements

- **New project only** - Must be created during contest period
- **Platform:** Must run on web, Android, or iOS
- **Stack:** Use Google Cloud + chosen partner's tools (no competing cloud platforms)
- **AI tools:** Only Google Cloud AI tools allowed (Gemini, BigQuery ML, etc.)
- **License:** Must include open-source license in repository

---

## Judging Criteria

**Stage 1:** Pass/fail baseline viability check (meets all requirements)

**Stage 2:** Equal-weighted scoring on:
- **Technological Implementation** - Quality of Google Cloud + partner integration
- **Design** - User experience and thoughtful design
- **Potential Impact** - Impact on target communities
- **Idea Quality** - Creativity and uniqueness

---

## Key Dates

- **Contest Period:** May 5 - June 11, 2026
- **Credit Application Deadline:** June 4, 2026
- **Submission Deadline:** June 11, 2026, 2:00 P.M. PT
- **Judging Period:** June 22 - July 6, 2026
- **Winners Announced:** ~July 7, 2026

---

## Quick Checklist

- [ ] Choose a partner track
- [ ] Apply for Google Cloud credits
- [ ] Plan your agent's real-world problem
- [ ] Build with Google Cloud Agent Builder
- [ ] Integrate partner's MCP server
- [ ] Create demo video
- [ ] Push code to public GitHub repo with license
- [ ] Deploy hosted version
- [ ] Submit on Devpost


