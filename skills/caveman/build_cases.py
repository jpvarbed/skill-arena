#!/usr/bin/env python3
"""Source of truth for caveman compression/fidelity cases."""
import json
from pathlib import Path


CASES = [
    {
        "id": "cv-tech-pooling",
        "domain": "technical explanation",
        "input": """Database connection pooling is a performance pattern that keeps a small set of database connections open and reuses them across requests. Without a pool, every request may pay the cost of opening a TCP connection, negotiating TLS, authenticating, and warming server-side state. That setup can dominate latency for short queries. A pool also protects the database by capping concurrent connections, which matters because many databases slow down or reject work when connection counts spike. The tradeoff is that the pool must be sized for real workload shape, not wishful peak traffic. Too small and requests wait behind idle transactions. Too large and the application simply moves overload into the database. The operational rule is to set timeouts, close leaked connections, and measure queue wait separately from query time.""",
        "reference_compression": "DB pool = reuse small open conn set across reqs. Avoid TCP/TLS/auth setup latency. Caps concurrent DB conn -> protects DB from spikes. Size to workload: too small -> wait behind idle tx; too large -> overload DB. Set timeouts, close leaks, measure queue wait separate from query time.",
        "probes": [
            {"question": "What setup costs does pooling avoid?", "answer_pattern": r"TCP.*TLS.*auth"},
            {"question": "What does the pool cap protect?", "answer_pattern": r"concurrent.*DB.*conn|DB.*from spikes"},
            {"question": "What should be measured separately?", "answer_pattern": r"queue wait.*query time"},
        ],
    },
    {
        "id": "cv-meeting-notes",
        "domain": "meeting notes",
        "input": """The team agreed to keep the July launch scope narrow and move the dashboard redesign to the next cycle. The only launch blocker is the export job, which still times out when a workspace has more than fifty thousand rows. Priya will split the job into batches and add progress events by Wednesday. Marco will update the help article after the API wording is final. We decided not to add another approval step because support tickets show that admins already understand the current review flow. The metrics review stays on Friday, but the team wants the report to separate activation from weekly retention so the launch decision is not based on a blended number.""",
        "reference_compression": "July launch scope stays narrow. Dashboard redesign moves next cycle. Blocker: export job times out over 50k rows. Priya batches job + progress events by Wednesday. Marco updates help article after API wording final. No extra approval step. Friday metrics report must split activation vs weekly retention.",
        "probes": [
            {"question": "What was moved to the next cycle?", "answer_pattern": r"dashboard redesign"},
            {"question": "What threshold triggers timeout?", "answer_pattern": r"50k|fifty thousand"},
            {"question": "Which metrics must be separated?", "answer_pattern": r"activation.*weekly retention"},
        ],
    },
    {
        "id": "cv-incident-summary",
        "domain": "incident summary",
        "input": """At 09:42 UTC the payments worker began retrying successful charges because the idempotency cache was unavailable in one region. The gateway returned success, but our worker could not persist the completion marker and treated the call as unknown. The retry loop created duplicate authorization attempts for 312 customers before the circuit breaker opened at 10:08 UTC. No captured charges were duplicated, but some customers saw temporary holds. The immediate fix was to fail closed when the idempotency store is unavailable. The follow-up is to move completion markers into the same durable write as the order state, then backfill a monitor that alerts on authorization attempts per order above one.""",
        "reference_compression": "09:42 UTC payments worker retried successful charges: idempotency cache unavailable in one region. Gateway success, completion marker not persisted -> worker treated call unknown. 312 customers got duplicate auth attempts before breaker at 10:08 UTC. No duplicated captured charges; some temp holds. Fix: fail closed when store unavailable. Follow-up: completion markers in durable order write + monitor auth attempts per order >1.",
        "probes": [
            {"question": "What failed?", "answer_pattern": r"idempotency cache|idempotency store"},
            {"question": "How many customers were affected?", "answer_pattern": r"312"},
            {"question": "Were captured charges duplicated?", "answer_pattern": r"No.*duplicated captured charges|captured charges.*not duplicated"},
        ],
    },
    {
        "id": "cv-product-spec",
        "domain": "product spec",
        "input": """The workspace export feature should let an owner download all project data as a zip file containing CSV tables and uploaded assets. The first version only supports manual exports from the settings page; scheduled exports are explicitly out of scope. An export request creates a job, emails the owner when the archive is ready, and expires the download link after seven days. The UI must show queued, running, failed, and ready states. If the job fails, the owner should see the last error message and a retry button. Success is measured by ninety five percent of exports under one gigabyte completing in less than ten minutes during the first week after launch.""",
        "reference_compression": "Workspace export: owner downloads zip with CSV tables + uploaded assets. V1 manual from settings only; scheduled exports out of scope. Request creates job, emails owner when archive ready, link expires after 7 days. UI states: queued, running, failed, ready. Failed job shows last error + retry. Success: 95% exports under 1GB finish under 10 min first launch week.",
        "probes": [
            {"question": "Who can download?", "answer_pattern": r"owner"},
            {"question": "What is out of scope?", "answer_pattern": r"scheduled exports"},
            {"question": "What is the success target?", "answer_pattern": r"95%.*under 1GB.*under 10 min"},
        ],
    },
    {
        "id": "cv-migration-plan",
        "domain": "migration plan",
        "input": """The billing migration will move subscription state from the legacy invoices table into the new entitlements service. Phase one is read-only shadowing: every invoice update writes an equivalent entitlement record, but product code still reads the old table. Phase two switches reads for internal workspaces after parity stays above 99.9 percent for seven days. Phase three enables the new service for all customers and keeps the old table as a rollback source for thirty days. The migration must preserve cancelled subscriptions because support uses them to answer refund questions. The main risk is timezone normalization, since the legacy table stores renewal dates in local account time and the new service stores UTC instants.""",
        "reference_compression": "Billing migration moves subscription state from legacy invoices to entitlements service. Phase 1 read-only shadow: invoice update writes entitlement, product still reads old table. Phase 2 switch internal reads after parity >99.9% for 7 days. Phase 3 all customers, old table rollback source 30 days. Preserve cancelled subscriptions for support refunds. Main risk: timezone normalization, local account renewal dates vs UTC instants.",
        "probes": [
            {"question": "What is phase one?", "answer_pattern": r"read-only shadow"},
            {"question": "What parity threshold gates phase two?", "answer_pattern": r"99\.9%.*7 days"},
            {"question": "What is the main risk?", "answer_pattern": r"timezone normalization"},
        ],
    },
    {
        "id": "cv-data-analysis",
        "domain": "data analysis",
        "input": """The retention analysis compared teams that enabled shared templates in their first week with teams that did not. Activation was similar across both groups, but week four retention was twelve points higher for teams that created at least three templates and invited five or more members. The effect disappears for teams with only one template, which suggests the feature matters when it becomes a team habit rather than a one-off setup step. The dataset excludes trials started after June fifteenth because they have not had enough time to reach the week four window. The next analysis should split by company size because enterprise teams may get template value from compliance workflows while small teams use them for onboarding.""",
        "reference_compression": "Retention analysis: teams enabling shared templates in first week vs not. Activation similar. Week 4 retention +12 points for teams with at least 3 templates and 5+ invited members. Effect disappears with only 1 template -> team habit, not one-off setup. Excludes trials after June 15: not enough week 4 window. Next split by company size: enterprise compliance vs small-team onboarding.",
        "probes": [
            {"question": "How much higher was week four retention?", "answer_pattern": r"12 points|\+12"},
            {"question": "Which trials were excluded?", "answer_pattern": r"after June 15"},
            {"question": "What split is next?", "answer_pattern": r"company size"},
        ],
    },
    {
        "id": "cv-security-review",
        "domain": "security review",
        "input": """The security review found that the webhook signature check is correct for current requests but unsafe for replay protection. The handler verifies the HMAC over the raw body and rejects unknown senders, so forged payloads should fail. However, the timestamp tolerance is set to twenty four hours because an old integration retried delayed events during an outage. That window lets a captured payload be replayed long after the user action. The recommendation is to reduce tolerance to five minutes, store recently seen delivery IDs for one day, and add a migration note for the old integration. This is a defense-in-depth issue, not evidence of a live exploit.""",
        "reference_compression": "Security review: webhook signature check OK for current reqs, replay protection weak. HMAC over raw body + unknown sender reject -> forged payloads fail. Timestamp tolerance 24h due old delayed retries, allows captured payload replay long after action. Recommend 5 min tolerance, store seen delivery IDs 1 day, migration note for old integration. Defense-in-depth, no live exploit evidence.",
        "probes": [
            {"question": "What is currently correct?", "answer_pattern": r"HMAC.*raw body"},
            {"question": "What is unsafe?", "answer_pattern": r"replay protection"},
            {"question": "What tolerance is recommended?", "answer_pattern": r"5 min|five minutes"},
        ],
    },
    {
        "id": "cv-onboarding",
        "domain": "onboarding guide",
        "input": """New support engineers should spend their first morning reading the refund policy, the escalation matrix, and the saved replies for account access. In the afternoon, they shadow two live conversations and write a short note about what information was missing at the start of each case. On day two they can answer low-risk billing questions, but a senior reviewer must approve any message that mentions legal terms, data deletion, or custom contracts. The goal is not to memorize every policy. The goal is to learn when a question is routine, when it needs evidence from logs, and when it should move to engineering or legal without delay.""",
        "reference_compression": "Support onboarding: first morning read refund policy, escalation matrix, saved replies for account access. Afternoon shadow 2 live conversations + note missing initial info. Day 2 answer low-risk billing; senior reviewer approves messages mentioning legal terms, data deletion, custom contracts. Goal not memorization. Learn routine vs log-evidence vs escalate to engineering/legal.",
        "probes": [
            {"question": "What should they read first?", "answer_pattern": r"refund policy.*escalation matrix.*saved replies"},
            {"question": "How many conversations do they shadow?", "answer_pattern": r"2|two"},
            {"question": "Which topics require senior approval?", "answer_pattern": r"legal terms.*data deletion.*custom contracts"},
        ],
    },
    {
        "id": "cv-research-summary",
        "domain": "research summary",
        "input": """The paper argues that instruction hierarchy failures become more common as the number of active layers increases. Models often follow a lower-priority instruction when it is more recent, more specific, or phrased more forcefully, even when the correct answer is to obey the higher tier. The practical lesson for agents is to make precedence explicit instead of relying on the model to infer it. The authors also separate true contradictions from override cases, which matters because an override can be safe when the lower layer is scoped and the higher layer allows it. A useful audit should therefore list the active tiers, quote the conflicting directives, and state whether precedence resolves the mismatch.""",
        "reference_compression": "Paper: instruction hierarchy failures rise as active layers increase. Models follow lower-priority instruction when recent, specific, or forceful, even if higher tier should win. Practical lesson: make precedence explicit. Separate true contradictions from override cases; override safe when lower layer scoped and higher layer allows. Audit should list tiers, quote conflicting directives, state whether precedence resolves mismatch.",
        "probes": [
            {"question": "What increases failures?", "answer_pattern": r"active layers increase|layers increases"},
            {"question": "What lower-priority traits mislead models?", "answer_pattern": r"recent.*specific.*forceful"},
            {"question": "What should the audit list?", "answer_pattern": r"tiers.*quote.*directives.*precedence"},
        ],
    },
    {
        "id": "cv-support-summary",
        "domain": "customer support",
        "input": """The customer reports that invited teammates can see the workspace name but cannot open any projects. The audit log shows that the owner changed the default role from editor to viewer yesterday, then imported twenty four users from a CSV file. Viewers can open shared dashboards but not private projects, so the behavior matches the current permission model. The likely fix is to bulk update the imported users to editor or share the specific projects with the viewer group. Before replying, confirm whether the owner intended the imported users to edit project data or only read dashboards, because those paths have different security implications.""",
        "reference_compression": "Customer: invited teammates see workspace name but cannot open projects. Audit log: owner changed default role editor -> viewer yesterday, then imported 24 users from CSV. Viewers can open shared dashboards, not private projects. Behavior matches permission model. Fix: bulk update imported users to editor or share specific projects with viewer group. Before reply, confirm intended edit project data vs read dashboards; security differs.",
        "probes": [
            {"question": "What role changed?", "answer_pattern": r"editor.*viewer"},
            {"question": "How many users were imported?", "answer_pattern": r"24"},
            {"question": "What should be confirmed?", "answer_pattern": r"edit project data.*read dashboards"},
        ],
    },
    {
        "id": "cv-design-critique",
        "domain": "design critique",
        "input": """The dashboard layout is visually calm, but it hides the comparison users need most. Current month revenue, churn risk, and expansion pipeline appear in separate cards with different scales, so the user has to remember numbers while moving across the page. The better structure is a single account health table with sortable columns and a compact trend sparkline per account. Cards can stay for the executive summary, but they should not be the primary workflow surface. The critique is not about making the page denser for its own sake. It is about putting repeated comparison and triage tasks into a shape that supports scanning.""",
        "reference_compression": "Dashboard calm, but hides needed comparison. Current month revenue, churn risk, expansion pipeline split across cards with different scales -> user memorizes numbers across page. Better: account health table with sortable columns + compact trend sparkline per account. Cards can stay for exec summary, not primary workflow. Goal not density; support repeated comparison + triage scanning.",
        "probes": [
            {"question": "What comparison is hidden?", "answer_pattern": r"revenue.*churn risk.*expansion pipeline"},
            {"question": "What structure is better?", "answer_pattern": r"account health table"},
            {"question": "What task should the shape support?", "answer_pattern": r"comparison.*triage.*scanning"},
        ],
    },
    {
        "id": "cv-release-notes",
        "domain": "release notes",
        "input": """This release adds saved filters to the activity feed, improves CSV export reliability, and fixes a bug where archived projects appeared in workspace search. Saved filters are available to all users and sync across devices. The export change retries failed chunks up to three times and marks partial archives as failed instead of ready, which prevents users from downloading incomplete files. Search indexing now excludes archived project IDs during the nightly rebuild and during immediate updates after a project is archived. There is no schema migration in this release, but the export worker must be restarted so it picks up the new retry policy.""",
        "reference_compression": "Release: saved filters for activity feed, better CSV export reliability, archived projects removed from workspace search. Saved filters all users, sync across devices. Export retries failed chunks up to 3 times and marks partial archives failed, not ready -> no incomplete downloads. Search indexing excludes archived project IDs during nightly rebuild + immediate archive updates. No schema migration. Restart export worker for new retry policy.",
        "probes": [
            {"question": "What feature was added?", "answer_pattern": r"saved filters"},
            {"question": "How many retries?", "answer_pattern": r"3|three"},
            {"question": "What must be restarted?", "answer_pattern": r"export worker"},
        ],
    },
]


PADDING = {
    "cv-tech-pooling": " The explanation is meant for an application engineer deciding whether latency is caused by query planning or connection setup. It should keep the operational distinction clear because a query optimization will not fix queue wait, and a larger pool will not fix a slow index.",
    "cv-meeting-notes": " The notes are for teammates who missed the call and need ownership, scope, and launch criteria without listening to the recording. They should preserve dates and names because the next standup will use them to check whether the export blocker moved.",
    "cv-incident-summary": " The summary will be pasted into a customer-facing incident review after support removes internal hostnames. It should distinguish authorization holds from captured charges because finance and support use different language when explaining temporary bank-visible activity.",
    "cv-product-spec": " The spec is for engineering planning, not marketing copy. It should preserve excluded scope and the measurable launch bar because otherwise a model can make the feature sound complete while dropping the parts that decide whether the first release ships.",
    "cv-migration-plan": " The plan will be used by an on-call engineer during the rollout window. It should keep phase gates, rollback duration, and preserved historical records visible because those are the facts someone needs when deciding whether to pause or continue.",
    "cv-data-analysis": " The analysis is for a product review where people may overread correlation as a universal rule. It should keep the cohort definition and exclusion window because the conclusion changes if immature trials or one-template teams are mixed into the comparison.",
    "cv-security-review": " The review is for a prioritization meeting. It should avoid implying a breach, but it must keep the replay mechanism and proposed controls intact because the work only makes sense if the risk and mitigation stay connected.",
    "cv-onboarding": " The guide is for a manager scheduling the first two days of training. It should preserve the approval boundary because new support engineers can answer routine questions early, but legal, deletion, and contract language need a reviewer.",
    "cv-research-summary": " The summary is for agents that need to apply the research, not cite it ceremonially. It should keep the distinction between contradiction and override because treating every difference as a conflict creates noisy audits that users stop trusting.",
    "cv-support-summary": " The support note is for drafting a reply without changing permissions blindly. It should preserve the diagnostic evidence from the audit log and the question for the owner because the correct fix depends on intended access, not only symptoms.",
    "cv-design-critique": " The critique is for a product designer deciding what to change first. It should keep the workflow reason for the table because otherwise the recommendation sounds like a generic density preference instead of a response to repeated comparison work.",
    "cv-release-notes": " The notes are for an operator preparing the deploy. They should preserve the worker restart requirement because no schema migration can make the release feel safer than it is, while a missed restart would leave the retry policy inactive.",
}


def expanded_case(case):
    case = dict(case)
    case["input"] = case["input"] + PADDING[case["id"]] + " Keep dates, counts, owners, risks, and exceptions intact."
    return case


def write_cases(path):
    Path(path).write_text("\n".join(json.dumps(expanded_case(case), sort_keys=True) for case in CASES) + "\n")


if __name__ == "__main__":
    write_cases(Path(__file__).with_name("cases.jsonl"))
