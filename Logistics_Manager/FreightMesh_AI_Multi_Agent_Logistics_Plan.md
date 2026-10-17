# FreightMesh AI --- Multi-Agent Freight Consolidation & Logistics Optimization

## 1. Project Overview

**FreightMesh AI** is a simulated multi-agent logistics network where AI
agents representing different companies collaborate to discover,
evaluate, negotiate, and approve freight-consolidation opportunities.

The core idea is:

> Companies frequently have partially loaded trucks, empty return trips,
> and shipments traveling along overlapping routes. Instead of
> independently arranging transportation, AI operator agents can
> communicate with one another and find opportunities to share available
> capacity while respecting cost, capacity, compatibility, route, and
> delivery-SLA constraints.

The system is designed specifically as a **Google ADK / Gemini / Google
Cloud hackathon project**.

The goal is not to build a real-world logistics marketplace. The goal is
to demonstrate a convincing **agentic decision-making system over a
simulated logistics environment**.

------------------------------------------------------------------------

# 2. Problem Statement

## Simple version

Many logistics companies move partially loaded trucks while other
companies have shipments traveling on the same or nearby routes.

This causes:

-   Higher transportation costs
-   Underutilized trucks
-   Empty return trips
-   More vehicles on the road
-   Wasted fuel
-   Higher carbon emissions

### Example

Blinkit has:

``` text
Mumbai → Hyderabad → Chennai

Truck capacity: 10 tons
Current load: 6 tons
Available capacity: 4 tons
```

Zepto has:

``` text
Hyderabad → Chennai

Shipment: 3 tons
Deadline: 10 PM
```

Instead of Zepto hiring another truck, an AI system can discover that
Blinkit's truck already has enough capacity and is traveling toward
Chennai.

The system checks:

-   Is there enough capacity?
-   Is the cargo compatible?
-   Will the shipment arrive before the deadline?
-   Does the route make sense?
-   Is sharing actually cheaper?
-   Does the truck need an additional detour?
-   Is the operator willing to share capacity?

If everything is valid:

``` text
Blinkit truck
       +
Zepto shipment
       ↓
Same vehicle
       ↓
Chennai
```

Result:

-   Lower cost
-   Higher truck utilization
-   Fewer empty/underutilized trips
-   Potentially lower emissions

------------------------------------------------------------------------

# 3. Better Hackathon Problem Statement

## Dynamic Freight Consolidation & Backhaul Optimization

Large retailers, e-commerce companies, manufacturers, and logistics
providers frequently operate partially loaded vehicles and empty return
trips. At the same time, other companies may have compatible shipments
traveling along similar routes and time windows.

Identifying these opportunities manually is difficult because logistics
teams must simultaneously consider:

-   Vehicle capacity
-   Shipment compatibility
-   Routes
-   Delivery deadlines
-   SLAs
-   Cost
-   Pickup windows
-   Operational constraints
-   Company-specific policies

### Proposed solution

Build an AI-powered multi-agent logistics network where each company is
represented by an **Operator Agent**.

These agents communicate with a central **Logistics Coordinator Agent**
to:

1.  Discover available truck capacity.
2.  Find compatible shipments.
3.  Evaluate routes and delivery times.
4.  Check operational constraints.
5.  Negotiate possible consolidation.
6.  Calculate expected cost and savings.
7.  Recommend the best transportation plan.
8.  Recalculate when conditions change.

The user can interact with the system conversationally.

Examples:

> "Find opportunities to reduce today's Chennai transportation cost."

> "Why did you choose this truck?"

> "What if the delivery deadline moves by two hours?"

> "What if I prioritize carbon reduction over cost?"

------------------------------------------------------------------------

# 4. One-Line Pitch

## Professional

> **FreightMesh AI is a multi-agent logistics network where AI operators
> representing different companies collaborate to turn underutilized
> truck capacity into optimized shared transportation.**

## More catchy

> **AI agents that help companies share freight capacity the way people
> share rides.**

## Strongest hackathon framing

> **We don't just find trucks. We let AI agents representing different
> businesses negotiate how the logistics network should move shipments
> more efficiently.**

------------------------------------------------------------------------

# 5. Why This Should Be an Agentic System

A normal optimization system could simply query a database:

``` text
Database
   ↓
Optimization algorithm
   ↓
Best truck
```

But real logistics networks involve multiple organizations.

Each organization has:

-   Different priorities
-   Different deadlines
-   Different cost limits
-   Different policies
-   Different operational constraints
-   Potentially private information

Therefore the architecture becomes:

``` text
                    Coordinator Agent
                         |
             +-----------+-----------+
             |           |           |
             ↓           ↓           ↓
         Blinkit       Zepto       Amazon
          Agent         Agent        Agent
             |           |           |
             +-----------+-----------+
                         |
                  Decision Engine
```

The agents communicate and negotiate instead of exposing everything to
one centralized LLM.

The LLM is responsible for:

-   Understanding natural language
-   Coordinating agents
-   Requesting information
-   Negotiating
-   Explaining decisions
-   Handling what-if questions

Deterministic code is responsible for:

-   Capacity calculations
-   Cost calculations
-   Route calculations
-   SLA calculations
-   Constraint validation
-   Candidate ranking

This separation is critical.

------------------------------------------------------------------------

# 6. Core Architecture

``` text
                         USER
                           |
                           v
                +----------------------+
                | Logistics Manager     |
                | / Conversational Agent|
                +----------+-----------+
                           |
                           v
                +----------------------+
                | Network Coordinator  |
                | Agent                |
                +----------+-----------+
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
   +-------------+  +-------------+  +-------------+
   | Blinkit     |  | Zepto       |  | Amazon      |
   | Operator    |  | Operator    |  | Operator    |
   | Agent       |  | Agent       |  | Agent       |
   +-------------+  +-------------+  +-------------+
          |                |                |
          +----------------+----------------+
                           |
                           v
                +----------------------+
                | Compliance / Risk    |
                | Agent                |
                +----------+-----------+
                           |
                           v
                +----------------------+
                | Deterministic        |
                | Optimization Engine  |
                +----------+-----------+
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
        Firestore     Maps Routes     Pub/Sub
        Simulation       API          Events
```

------------------------------------------------------------------------

# 7. Agents

## 7.1 Logistics Manager Agent

### Purpose

The user-facing conversational agent.

### Responsibilities

-   Understand the user's objective.
-   Convert natural-language requests into structured requirements.
-   Ask the Coordinator to solve the problem.
-   Explain the result.
-   Answer follow-up questions.
-   Trigger what-if simulations.

### Example

User:

> Find the cheapest way to move today's Chennai shipments.

Manager Agent converts this into something like:

``` json
{
  "objective": "minimize_transportation_cost",
  "destination": "Chennai",
  "deadline": "2026-10-18T22:00",
  "allow_delay_hours": 0
}
```

------------------------------------------------------------------------

# 8. Network Coordinator Agent

This is the central orchestration agent.

### Responsibilities

1.  Understand the optimization objective.
2.  Identify relevant shipments.
3.  Ask operator agents for capacity.
4.  Generate possible consolidation combinations.
5.  Call deterministic tools.
6.  Ask Compliance Agent to validate candidates.
7.  Ask company agents to accept/reject offers.
8.  Compare feasible plans.
9.  Select the best plan.
10. Explain the reasoning.

### Mental model

Think of it as:

> **AI project manager for the logistics network.**

------------------------------------------------------------------------

# 9. Company Operator Agents

Create at least three simulated company agents.

## 9.1 Blinkit Operator Agent

Knows:

-   Blinkit trucks
-   Blinkit shipments
-   Blinkit warehouses
-   Blinkit policies
-   Blinkit priorities

Example policy:

``` python
MAX_SHARED_CAPACITY = 0.90
MIN_OPERATIONAL_BUFFER = 0.10
ALLOW_SHARED_CARGO = True
```

The agent should protect Blinkit's own SLA first.

------------------------------------------------------------------------

## 9.2 Zepto Operator Agent

Knows:

-   Zepto shipments
-   Zepto transportation requirements
-   Zepto maximum acceptable cost
-   Zepto deadlines

Example policy:

``` python
MAX_ACCEPTABLE_COST = 15000
MAX_ACCEPTABLE_DELAY_HOURS = 1
```

------------------------------------------------------------------------

## 9.3 Amazon Operator Agent

Knows:

-   Amazon shipments
-   Amazon trucks
-   Amazon deadlines
-   Amazon cost preferences

Example policy:

``` python
MAX_DELAY_HOURS = 2
PREFER_LOW_COST = True
```

------------------------------------------------------------------------

# 10. Compliance / Risk Agent

This agent prevents invalid recommendations.

It checks:

## Vehicle

-   Maximum weight
-   Maximum volume
-   Vehicle type
-   Remaining capacity
-   Operational buffer

## Shipment

-   Cargo type
-   Fragility
-   Hazardous material
-   Temperature requirements
-   Special handling

## Delivery

-   Pickup window
-   Delivery deadline
-   SLA

## Route

-   Route compatibility
-   Additional distance
-   Additional time
-   Detour

The system must never recommend a consolidation that violates a hard
constraint.

------------------------------------------------------------------------

# 11. Optimization Engine

The optimization engine should be deterministic.

The LLM should not be responsible for arithmetic.

### Input

``` text
Shipments
Trucks
Routes
Company policies
Deadlines
Costs
Constraints
```

### Output

``` text
Best feasible plan
```

------------------------------------------------------------------------

# 12. Optimization Factors

## 12.1 Shipment factors

-   Origin
-   Destination
-   Weight
-   Volume
-   Dimensions
-   Cargo type
-   Priority
-   Pickup window
-   Delivery deadline
-   SLA
-   Fragility
-   Temperature requirement
-   Hazardous flag

------------------------------------------------------------------------

## 12.2 Truck factors

-   Current location
-   Current load
-   Maximum capacity
-   Remaining capacity
-   Vehicle type
-   Current route
-   Destination
-   ETA
-   Available time
-   Operating cost per kilometer
-   Fuel efficiency

------------------------------------------------------------------------

## 12.3 Route factors

-   Distance
-   Travel time
-   Traffic
-   Tolls
-   Pickup detour
-   Delivery detour
-   Number of stops
-   Route overlap

Google Maps Routes API / Route Matrix can be used for real distance and
duration calculations.

------------------------------------------------------------------------

## 12.4 Business factors

-   Transportation cost
-   Potential savings
-   SLA risk
-   Truck utilization
-   Empty kilometers
-   Carbon emissions
-   Company preferences
-   Sharing permissions

------------------------------------------------------------------------

# 13. Suggested Scoring Function

For the hackathon MVP, do not build an unnecessarily complex
mathematical model.

Use a weighted score:

``` text
SCORE =

  Cost Saving
+ Capacity Utilization
+ Route Efficiency
+ Empty KM Reduction
+ Carbon Reduction
- SLA Risk
- Extra Distance
- Delay Risk
- Compatibility Risk
```

Example:

``` text
Candidate A

Cost saving:              +40
Capacity utilization:     +20
Route efficiency:         +15
Empty KM reduction:       +10
SLA risk:                   0
Extra distance:            -5
Compatibility risk:        0

TOTAL = 80
```

Candidate B:

``` text
Cost saving:              +30
Capacity utilization:     +25
Route efficiency:         +10
SLA risk:                 -20
Extra distance:            -5

TOTAL = 40
```

Candidate A wins.

------------------------------------------------------------------------

# 14. Hard Constraints vs Soft Objectives

This distinction is important.

## Hard constraints

These must never be violated.

``` text
Capacity
Cargo compatibility
Vehicle restrictions
Pickup window
Delivery deadline
Legal/operational constraints
```

## Soft objectives

These can be optimized.

``` text
Cost
Utilization
Empty kilometers
Carbon emissions
Number of trucks
Number of stops
```

The system should first eliminate invalid solutions and only then rank
valid ones.

------------------------------------------------------------------------

# 15. Simulation Environment

Because real company logistics data is unavailable, create a simulated
logistics world.

Call it:

``` text
LogisticsWorld
```

It contains:

``` text
Companies
Warehouses
Trucks
Shipments
Routes
Events
Policies
Costs
```

------------------------------------------------------------------------

# 16. Simulated Companies

Start with:

``` text
Blinkit
Zepto
Amazon
```

Don't start with 10 companies.

Three is enough to demonstrate multi-agent collaboration.

------------------------------------------------------------------------

# 17. Simulated Cities

Use:

``` text
Mumbai
Hyderabad
Bangalore
Chennai
Pune
```

Example routes:

``` text
Mumbai → Hyderabad
Hyderabad → Chennai
Bangalore → Chennai
Mumbai → Pune
Pune → Hyderabad
```

------------------------------------------------------------------------

# 18. Example Trucks

``` json
{
  "truck_id": "BLK-001",
  "company": "Blinkit",
  "current_location": "Mumbai",
  "route": [
    "Mumbai",
    "Hyderabad",
    "Chennai"
  ],
  "capacity_tons": 10,
  "current_load_tons": 6,
  "available_capacity_tons": 4
}
```

Another:

``` json
{
  "truck_id": "ZEP-001",
  "company": "Zepto",
  "current_location": "Hyderabad",
  "route": [
    "Hyderabad",
    "Chennai"
  ],
  "capacity_tons": 8,
  "current_load_tons": 2,
  "available_capacity_tons": 6
}
```

------------------------------------------------------------------------

# 19. Example Shipments

``` json
{
  "shipment_id": "ZEP-SHP-001",
  "company": "Zepto",
  "origin": "Hyderabad",
  "destination": "Chennai",
  "weight_tons": 3,
  "deadline": "22:00",
  "priority": "HIGH",
  "cargo_type": "ELECTRONICS"
}
```

Another:

``` json
{
  "shipment_id": "AMZ-SHP-001",
  "company": "Amazon",
  "origin": "Hyderabad",
  "destination": "Chennai",
  "weight_tons": 2,
  "deadline": "21:00",
  "priority": "MEDIUM",
  "cargo_type": "GENERAL"
}
```

------------------------------------------------------------------------

# 20. Simulation Events

Make the environment dynamic.

Supported events:

``` text
NEW_SHIPMENT
TRUCK_DELAYED
TRUCK_BREAKDOWN
TRUCK_CAPACITY_CHANGED
SHIPMENT_CANCELLED
DEADLINE_CHANGED
TRAFFIC_INCREASED
ROUTE_BLOCKED
```

Example:

``` text
12:00

Blinkit Truck BLK-001
Hyderabad → Chennai
40% capacity available

12:05

Zepto creates:
Hyderabad → Chennai
3 ton shipment

12:05

NEW_SHIPMENT event

12:05

Coordinator Agent wakes up

12:06

Agents communicate

12:07

Consolidation opportunity found
```

------------------------------------------------------------------------

# 21. Agent Communication

The most important part of the demo is showing agents communicating.

Example:

``` text
Coordinator → Blinkit Agent

Do you have usable capacity for
Hyderabad → Chennai?
```

Blinkit:

``` text
BLK-001 has 4 tons of usable capacity.

ETA Chennai: 19:40.

Can accept up to 3 tons while maintaining
the required operational buffer.
```

Coordinator:

``` text
Zepto Agent, can shipment ZEP-001
be delivered by 19:40?
```

Zepto:

``` text
Yes.

Required delivery time: 22:00.
```

Coordinator:

``` text
Compliance Agent:
Check cargo compatibility.
```

Compliance:

``` text
Compatible.

Capacity sufficient.

SLA satisfied.

Route feasible.
```

Coordinator:

``` text
Optimization Engine:

Shared cost: ₹11,200
Dedicated cost: ₹19,600
Estimated saving: ₹8,400
```

Coordinator:

``` text
Recommended:
Consolidate ZEP-001 onto BLK-001.
```

------------------------------------------------------------------------

# 22. Negotiation

Give each operator agent its own policy.

For example:

``` text
Coordinator:
Can Blinkit accept 3 tons?
```

Blinkit:

``` text
Yes, but I require a 1-ton operational buffer.
```

Coordinator:

``` text
Zepto shipment is 3 tons.

Estimated cost is ₹11,200.

ETA is 20:15.

Does this meet your SLA?
```

Zepto:

``` text
Yes.

Accept.
```

Coordinator:

``` text
Blinkit accepts?
```

Blinkit:

``` text
Accepted.
```

Then:

``` text
CONSOLIDATION APPROVED
```

------------------------------------------------------------------------

# 23. Why Negotiation Matters

This makes the project genuinely multi-agent.

Instead of:

``` text
Central AI
    ↓
Read everything
    ↓
Make decision
```

you demonstrate:

``` text
                  Coordinator

              /       |       \
             /        |        \
        Blinkit     Zepto     Amazon
          Agent       Agent     Agent
             \         |        /
              \        |       /
                Negotiation
                     |
                  Decision
```

Each agent can protect its company's interests.

------------------------------------------------------------------------

# 24. Private Information Simulation

To make the agent architecture more realistic, do not expose all company
information to the Coordinator.

For example:

### Blinkit knows

``` text
Internal truck cost
Operational buffer
Sharing policy
Truck availability
Internal priority
```

### Zepto knows

``` text
Maximum acceptable cost
Shipment urgency
Internal SLA
```

The Coordinator has to ask the agents for information.

This demonstrates decentralized cooperation.

------------------------------------------------------------------------

# 25. ADK Tools

Give agents narrow tools.

## Fleet tools

``` text
get_available_trucks()
get_truck(truck_id)
get_remaining_capacity(truck_id)
get_truck_route(truck_id)
```

## Shipment tools

``` text
get_pending_shipments()
get_shipment(shipment_id)
get_company_shipments(company_id)
```

## Route tools

``` text
calculate_route()
calculate_eta()
calculate_detour()
calculate_route_matrix()
```

## Optimization tools

``` text
find_candidate_consolidations()
check_capacity()
check_sla()
check_compatibility()
calculate_cost()
calculate_savings()
rank_candidates()
```

## Negotiation tools

``` text
request_capacity()
make_offer()
accept_offer()
reject_offer()
create_consolidation_plan()
```

------------------------------------------------------------------------

# 26. Tool Design Principle

Do not give the LLM a generic:

``` text
execute_sql()
```

or:

``` text
modify_database()
```

Instead provide narrow business tools:

``` text
find_available_trucks()
check_capacity()
calculate_savings()
```

This makes the system safer, easier to debug, and easier to demonstrate.

------------------------------------------------------------------------

# 27. Google Technology Stack

Recommended stack:

  Requirement           Google Technology
  --------------------- ------------------------------
  LLM                   Gemini
  Agent framework       Google ADK
  Agent orchestration   ADK multi-agent architecture
  Database              Firestore
  Events                Google Cloud Pub/Sub
  Routing               Google Maps Routes API
  Backend               Cloud Run
  Frontend              React / Firebase
  Analytics             BigQuery --- optional
  Monitoring            Cloud Logging / Trace

Keep the first version local and only deploy once the core agent works.

------------------------------------------------------------------------

# 28. Firestore Data Model

Suggested collections:

``` text
companies/
    blinkit
    zepto
    amazon

trucks/
    BLK-001
    BLK-002
    ZEP-001

shipments/
    SHP-001
    SHP-002
    SHP-003

warehouses/
    MUM-01
    HYD-01
    CHE-01

routes/
    MUM-HYD-CHE
    HYD-CHE
    BLR-CHE

optimization_runs/
    RUN-001
    RUN-002

negotiations/
    NEG-001
    NEG-002

events/
    EVT-001
    EVT-002
```

------------------------------------------------------------------------

# 29. Suggested Project Structure

``` text
freightmesh/
│
├── app/
│   │
│   ├── agents/
│   │   ├── manager_agent.py
│   │   ├── coordinator_agent.py
│   │   ├── company_agent.py
│   │   ├── blinkit_agent.py
│   │   ├── zepto_agent.py
│   │   ├── amazon_agent.py
│   │   ├── compliance_agent.py
│   │   └── optimization_agent.py
│   │
│   ├── tools/
│   │   ├── shipment_tools.py
│   │   ├── fleet_tools.py
│   │   ├── route_tools.py
│   │   ├── optimization_tools.py
│   │   ├── cost_tools.py
│   │   └── negotiation_tools.py
│   │
│   ├── simulation/
│   │   ├── world.py
│   │   ├── generator.py
│   │   ├── events.py
│   │   └── scenarios.py
│   │
│   ├── models/
│   │   ├── shipment.py
│   │   ├── truck.py
│   │   ├── company.py
│   │   ├── route.py
│   │   └── negotiation.py
│   │
│   └── config/
│       └── policies.py
│
├── frontend/
│
├── tests/
│
├── requirements.txt
└── README.md
```

------------------------------------------------------------------------

# 30. Coordinator Agent Instruction

Conceptual system instruction:

``` text
You are the FreightMesh Network Coordinator.

Your goal is to minimize transportation cost while maintaining
shipment SLAs and respecting vehicle and cargo constraints.

You do not directly calculate logistics values.

You must use tools for:
- capacity
- cost
- route
- ETA
- compatibility
- SLA

You may communicate with company operator agents.

Never recommend a consolidation unless:
1. Vehicle capacity is sufficient.
2. Cargo is compatible.
3. Pickup is feasible.
4. Delivery SLA is satisfied.
5. The consolidation produces a measurable benefit.

When multiple solutions exist:
1. Prefer SLA-safe solutions.
2. Prefer lower cost.
3. Prefer higher vehicle utilization.
4. Prefer fewer empty kilometers.
5. Prefer lower environmental impact.

Always explain why the selected plan is better.
```

------------------------------------------------------------------------

# 31. Blinkit Operator Agent Instruction

``` text
You are Blinkit's Logistics Operator Agent.

You represent Blinkit's operational interests.

Protect:
- Blinkit's shipment SLAs
- truck capacity
- delivery deadlines
- operational buffer

You may share unused truck capacity with other companies
when company policy permits.

Never sacrifice a Blinkit shipment SLA merely to help another company.

When asked for capacity:
- inspect available trucks
- calculate remaining usable capacity
- check route
- check ETA
- return an offer with constraints.

Do not reveal internal information unless it is required
for the negotiation.
```

------------------------------------------------------------------------

# 32. Manager Conversation Examples

## Example 1

User:

> Find me the cheapest way to deliver today's Chennai shipments.

Agent:

``` text
I found 3 consolidation opportunities.

The best option can reduce estimated transportation
cost by ₹10,700.

It increases truck utilization from 58% to 86%
without violating any delivery SLA.
```

------------------------------------------------------------------------

## Example 2

User:

> Why didn't you use Truck BLK-001?

Agent:

``` text
BLK-001 had 4 tons available, but adding the shipment
would exceed the required operational buffer and increase
the probability of an SLA violation.

BLK-002 was selected instead.
```

------------------------------------------------------------------------

## Example 3

User:

> What if I allow a 2-hour delay?

Agent:

``` text
Allowing a 2-hour delay creates two additional
consolidation opportunities.

Estimated additional savings: ₹6,200.

However, one high-priority shipment would still need
dedicated transportation.
```

------------------------------------------------------------------------

## Example 4

User:

> Prioritize carbon reduction instead of cost.

Agent:

``` text
I changed the optimization weights.

The recommended plan now reduces estimated empty
kilometers by 34% and CO₂ emissions by approximately 18%,
at an additional transportation cost of ₹2,400.
```

------------------------------------------------------------------------

# 33. Demo UI

Use three major panels.

``` text
+----------------------------------------------------------+
|                     FREIGHTMESH AI                       |
+----------------------+-----------------------------------+
|                      |                                   |
|     LIVE NETWORK     |       AGENT ACTIVITY              |
|                      |                                   |
|  🚚 BLK-001          | Coordinator → Blinkit              |
|  HYD → CHE           | "Available capacity?"             |
|  40% free            |                                   |
|                      | Blinkit → Coordinator              |
|  🚚 ZEP-003          | "4 tons available."               |
|  BLR → CHE           |                                   |
|  25% free            | Coordinator → Zepto                |
|                      | "Shipment deadline?"               |
|                      |                                   |
+----------------------+-----------------------------------+
|                                                          |
|  💬 Ask FreightMesh                                     |
|                                                          |
|  "Find the cheapest way to deliver today's Chennai       |
|   shipments."                                            |
|                                                          |
+----------------------------------------------------------+
```

------------------------------------------------------------------------

# 34. Optimization Result UI

Show:

``` text
OPTIMIZATION RESULT

Original estimated cost
₹32,400

Optimized cost
₹21,700

Estimated saving
₹10,700

Truck utilization
58% → 86%

Empty kilometers
412 → 190 km

SLA violations
0
```

Also show:

``` text
WHY THIS PLAN?

✓ Capacity available
✓ Route compatible
✓ Cargo compatible
✓ SLA satisfied
✓ Lower transportation cost
✓ Higher truck utilization
```

------------------------------------------------------------------------

# 35. Primary Demo Scenario

This should be your scripted hackathon demo.

## Initial state

Blinkit truck:

``` text
BLK-001

Mumbai → Hyderabad → Chennai

Capacity: 10 tons
Current load: 6 tons
Available: 4 tons
```

Zepto shipment:

``` text
ZEP-001

Hyderabad → Chennai

Weight: 3 tons
Deadline: 22:00
```

Amazon shipment:

``` text
AMZ-001

Hyderabad → Chennai

Weight: 2 tons
Deadline: 21:00
```

------------------------------------------------------------------------

# 36. Demo Step 1

User:

> Optimize all Hyderabad → Chennai shipments.

Coordinator:

``` text
Searching active shipments...

Found:

ZEP-001 — 3 tons
AMZ-001 — 2 tons
```

------------------------------------------------------------------------

# 37. Demo Step 2

Coordinator asks Blinkit:

``` text
Do you have available capacity?
```

Blinkit:

``` text
BLK-001 has 4 tons usable capacity.
```

------------------------------------------------------------------------

# 38. Demo Step 3 --- Deliberate Rejection

Coordinator tries:

``` text
ZEP-001 + AMZ-001
3 + 2 = 5 tons
```

Available:

``` text
4 tons
```

Result:

``` text
❌ Capacity exceeded
```

This is important because it proves the system does not blindly
consolidate everything.

------------------------------------------------------------------------

# 39. Demo Step 4

Suppose another truck exists:

``` text
BLK-002

Hyderabad → Chennai

Capacity: 8 tons
Available: 6 tons
```

Now:

``` text
ZEP-001 + AMZ-001

3 + 2 = 5 tons

Available = 6 tons

✓ Feasible
```

------------------------------------------------------------------------

# 40. Demo Step 5

Optimization engine:

``` text
Shared transportation cost:
₹21,700

Separate transportation cost:
₹32,400

Estimated saving:
₹10,700
```

Coordinator recommends:

``` text
BLK-002

5 / 8 tons

62.5% utilization
```

------------------------------------------------------------------------

# 41. Demo Step 6 --- What-If

User:

> What if Amazon's deadline changes to 19:00?

Suppose:

``` text
BLK-002 ETA = 20:15
```

Agent responds:

``` text
The previous consolidation is no longer feasible.

Amazon's SLA would be violated.

Recommended alternative:

Amazon → dedicated vehicle
Zepto → BLK-002
```

This demonstrates adaptive decision-making.

------------------------------------------------------------------------

# 42. Demo Step 7 --- Objective Change

User:

> What if I prioritize carbon reduction over cost?

Change optimization weights.

Original:

``` text
Cost             30%
SLA              30%
Utilization      15%
Empty KM         15%
CO₂              10%
```

New:

``` text
Cost             15%
SLA              25%
Utilization      20%
Empty KM         20%
CO₂              20%
```

The system recalculates and potentially chooses a different plan.

This is a powerful demonstration of dynamic decision-making.

------------------------------------------------------------------------

# 43. Event-Driven Demo

After the initial demo, simulate:

``` text
NEW_SHIPMENT
```

Example:

``` json
{
  "event": "NEW_SHIPMENT",
  "shipment_id": "ZEP-009",
  "origin": "Hyderabad",
  "destination": "Chennai",
  "weight": 3
}
```

Flow:

``` text
Simulation
    ↓
Pub/Sub
    ↓
Coordinator
    ↓
Find capacity
    ↓
Contact operators
    ↓
Check constraints
    ↓
Optimize
    ↓
Recommendation
```

This makes the system feel continuously active instead of being just a
chatbot.

------------------------------------------------------------------------

# 44. Backhaul Optimization

Add this as a second use case if time permits.

Example:

``` text
Truck:

Chennai → Hyderabad
████████████████
Full

Hyderabad → Chennai
░░░░░░░░░░░░░░░░
Empty
```

The Coordinator searches for:

``` text
Hyderabad → Chennai shipments
```

If it finds one:

``` text
Existing truck
       +
Return shipment
       ↓
Backhaul
```

Benefits:

-   Lower empty kilometers
-   Additional revenue
-   Better truck utilization
-   Lower transportation cost
-   Lower emissions

This is a very strong extension of the original idea.

------------------------------------------------------------------------

# 45. Development Roadmap

## Phase 1 --- Simulation

Build:

``` text
Company
Truck
Shipment
Warehouse
Route
```

Generate:

``` text
3 companies
10 trucks
30 shipments
5 cities
```

No AI yet.

Make sure these calculations work:

``` text
capacity
cost
ETA
SLA
utilization
```

------------------------------------------------------------------------

# 46. Phase 2 --- Optimization Engine

Implement:

``` text
find_candidates()
check_capacity()
check_compatibility()
check_sla()
calculate_cost()
calculate_savings()
rank_candidates()
```

You should be able to execute:

``` python
result = optimize_shipments()
```

and get:

``` text
Best option:

Truck: BLK-002

Shipments:
ZEP-001
AMZ-001

Cost:
₹21,700

Original cost:
₹32,400

Saving:
₹10,700

Utilization:
62.5%

SLA:
PASS
```

Do not start the LLM work until this works.

------------------------------------------------------------------------

# 47. Phase 3 --- First ADK Agent

Create:

``` text
Logistics Manager Agent
```

Give it:

``` text
get_shipments()
get_trucks()
optimize_shipments()
```

User:

> Find me the cheapest way to deliver today's shipments.

The agent calls the deterministic optimization engine.

------------------------------------------------------------------------

# 48. Phase 4 --- Multi-Agent

Add:

``` text
Blinkit Agent
Zepto Agent
Amazon Agent
Compliance Agent
Coordinator Agent
```

Test:

``` text
Coordinator
   ↓
Blinkit
   ↓
Zepto
   ↓
Compliance
   ↓
Optimization
```

------------------------------------------------------------------------

# 49. Phase 5 --- Negotiation

Implement:

``` text
request_capacity()
make_offer()
accept_offer()
reject_offer()
create_consolidation_plan()
```

Agents should exchange structured offers.

Example:

``` json
{
  "truck_id": "BLK-002",
  "available_capacity": 6,
  "route": "Hyderabad-Chennai",
  "eta": "20:15",
  "max_shareable_weight": 5,
  "conditions": [
    "No SLA violation",
    "Cargo compatible"
  ]
}
```

------------------------------------------------------------------------

# 50. Phase 6 --- Google Maps

Integrate:

``` text
Google Maps Routes API
```

Use it for:

``` text
distance
ETA
route compatibility
detour
route matrix
```

Cache common routes to reduce API usage.

------------------------------------------------------------------------

# 51. Phase 7 --- Pub/Sub

Create:

``` text
shipment-events
fleet-events
```

Example:

``` text
NEW_SHIPMENT
TRUCK_DELAYED
DEADLINE_CHANGED
TRUCK_BREAKDOWN
```

Coordinator subscribes to relevant events.

------------------------------------------------------------------------

# 52. Phase 8 --- Frontend

Only after the agent system works.

Build:

1.  Network map
2.  Agent activity feed
3.  Optimization result
4.  Conversation panel
5.  What-if controls

------------------------------------------------------------------------

# 53. Phase 9 --- Cloud Deployment

Deploy the working application to:

``` text
Cloud Run
```

Use:

``` text
Firestore
Pub/Sub
Google Maps
Gemini
ADK
```

Do not spend hackathon time prematurely building distributed
microservices for every agent.

A single ADK application containing multiple agents is sufficient for
the MVP.

------------------------------------------------------------------------

# 54. Recommended MVP Scope

If time becomes limited, implement only:

## Agents

``` text
1. Manager Agent
2. Coordinator Agent
3. Blinkit Operator Agent
4. Zepto Operator Agent
5. Compliance Agent
```

## Tools

``` text
get_shipments()
get_trucks()
check_capacity()
check_compatibility()
calculate_route()
calculate_cost()
calculate_savings()
create_plan()
```

## Simulation

``` text
3 companies
10 trucks
30 shipments
5 cities
```

## Google technologies

``` text
Gemini
Google ADK
Firestore
Google Maps Routes API
Pub/Sub
Cloud Run
```

## Demo

``` text
User asks
    ↓
Coordinator
    ↓
Operator agents communicate
    ↓
Constraints checked
    ↓
Optimization
    ↓
Negotiation
    ↓
Recommendation
    ↓
What-if question
    ↓
Reoptimization
```

------------------------------------------------------------------------

# 55. Important Engineering Principle

Do not create an LLM agent for everything.

Bad:

``` text
LLM calculates truck capacity
LLM calculates cost
LLM calculates distance
LLM decides if 5 tons fit into a 4-ton truck
```

Good:

``` text
LLM
 ↓
Orchestrates
 ↓
Deterministic tools
 ↓
Exact calculations
 ↓
LLM explains
```

For example:

``` text
LLM:
"Check whether ZEP-001 fits on BLK-002."

Tool:
capacity_check(
    available=6,
    shipment_weight=3
)

Tool result:
true

LLM:
"Capacity is sufficient."
```

This makes the system reliable.

------------------------------------------------------------------------

# 56. How to Answer "Why Agents?"

A judge may ask:

> Why can't this just be an optimization algorithm?

Answer:

> **The optimization itself is deterministic, but the logistics network
> is decentralized. Different businesses have different objectives,
> constraints, policies and private information. Our agents represent
> those businesses, communicate with one another, negotiate feasible
> options, invoke deterministic optimization tools, explain trade-offs,
> and adapt the plan when conditions change.**

Short version:

> **The optimization engine finds feasible plans. The agents coordinate
> the organizations required to make those plans possible.**

------------------------------------------------------------------------

# 57. What Makes This Different From a Chatbot

A chatbot:

``` text
User
 ↓
LLM
 ↓
Answer
```

FreightMesh:

``` text
User
 ↓
Manager Agent
 ↓
Coordinator
 ↓
Company Agents
 ↓
Negotiation
 ↓
Tools
 ↓
Optimization
 ↓
Compliance
 ↓
Decision
 ↓
Human approval
```

It has:

-   Multiple agents
-   Tool calls
-   External state
-   Negotiation
-   Constraints
-   Dynamic events
-   Optimization
-   What-if reasoning
-   Explainable decisions

------------------------------------------------------------------------

# 58. What Makes This Different From a Normal Optimization Algorithm

Normal optimization:

``` text
Input
 ↓
Algorithm
 ↓
Output
```

FreightMesh:

``` text
Input
 ↓
Agents understand intent
 ↓
Agents request information
 ↓
Operators negotiate
 ↓
Deterministic optimization
 ↓
Compliance validation
 ↓
Decision
 ↓
Explanation
 ↓
Human approval
```

The system is designed around **coordination between independent
actors**.

------------------------------------------------------------------------

# 59. What NOT to Build

Avoid these unless everything else is complete:

-   Real trucking marketplace
-   Real payments
-   Real insurance
-   Real driver management
-   Real fleet tracking
-   Complete TMS
-   15+ agents
-   Computer vision
-   IoT hardware
-   Real-world company integrations
-   Production-grade route optimization
-   Complex ML forecasting
-   Fully autonomous execution

These are distractions for a hackathon.

------------------------------------------------------------------------

# 60. Suggested Team Split

If you have multiple team members:

## Person 1 --- Agent/ADK

Own:

``` text
Manager Agent
Coordinator
Operator Agents
Agent communication
Prompts
```

## Person 2 --- Optimization

Own:

``` text
Simulation
Constraints
Cost
Capacity
SLA
Scoring
```

## Person 3 --- Google Cloud

Own:

``` text
Firestore
Pub/Sub
Maps
Cloud Run
```

## Person 4 --- Frontend

Own:

``` text
Map
Agent activity
Chat
Optimization results
What-if UI
```

If you're alone, follow the phases sequentially.

------------------------------------------------------------------------

# 61. Final Architecture

``` text
                         USER
                           |
                           v
                 +---------------------+
                 | Gemini + ADK        |
                 | Manager Agent       |
                 +----------+----------+
                            |
                            v
                 +---------------------+
                 | Network Coordinator |
                 | Agent               |
                 +----------+----------+
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
        +-----------+ +-----------+ +-----------+
        | Blinkit   | | Zepto     | | Amazon    |
        | Operator  | | Operator  | | Operator  |
        | Agent     | | Agent     | | Agent     |
        +-----------+ +-----------+ +-----------+
              \             |             /
               \            |            /
                +-----------+-----------+
                            |
                            v
                  +-------------------+
                  | Compliance Agent  |
                  +---------+---------+
                            |
                            v
                  +-------------------+
                  | Optimization      |
                  | Engine            |
                  +---------+---------+
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
          Firestore      Maps API      Pub/Sub
              |
              v
        Simulation World
              |
              v
           Cloud Run
```

------------------------------------------------------------------------

# 62. Final Hackathon Story

Your presentation should tell this story:

### Problem

``` text
Many trucks are not fully utilized.

At the same time, other companies are paying
for separate transportation on similar routes.
```

### Existing problem

``` text
The information is fragmented.

Company A doesn't know that Company B has
a shipment that could use its spare capacity.
```

### Solution

``` text
Give every company an AI logistics operator.
```

### Agents

``` text
Blinkit Agent
Zepto Agent
Amazon Agent
```

### Collaboration

``` text
Agents discover:
"Your truck has capacity."

"Your shipment needs this route."

"Can we share?"
```

### Decision

``` text
Check:

Capacity
Compatibility
Route
ETA
SLA
Cost
```

### Result

``` text
₹32,400
      ↓
₹21,700

Saving = ₹10,700
```

### Adaptation

Then:

> "What if the deadline changes?"

The agents renegotiate and recalculate.

### Final message

> **FreightMesh turns fragmented logistics operations into a
> collaborative agent network where businesses can intelligently share
> transportation capacity without sacrificing their operational
> constraints.**

------------------------------------------------------------------------

# 63. Implementation Priority

If you need to prioritize ruthlessly:

``` text
                    MUST HAVE
                        |
                        v
             +---------------------+
             | Simulation World    |
             +----------+----------+
                        |
                        v
             +---------------------+
             | Deterministic       |
             | Optimization Engine |
             +----------+----------+
                        |
                        v
             +---------------------+
             | ADK Coordinator     |
             +----------+----------+
                        |
                        v
             +---------------------+
             | Company Agents      |
             +----------+----------+
                        |
                        v
             +---------------------+
             | Negotiation         |
             +----------+----------+
                        |
                        v
             +---------------------+
             | Conversational UI   |
             +---------------------+

                    THEN

             Google Maps
                  ↓
               Pub/Sub
                  ↓
              Firestore
                  ↓
              Cloud Run
                  ↓
             Carbon scoring
                  ↓
             Backhaul
                  ↓
          Advanced what-if
```

------------------------------------------------------------------------

# 64. Definition of Done

The MVP is ready when this works end-to-end:

``` text
User:

"Find the cheapest way to move today's
Hyderabad → Chennai shipments."
```

Then:

``` text
Manager Agent
       ↓
Coordinator Agent
       ↓
Blinkit Agent
       ↓
Zepto Agent
       ↓
Compliance Agent
       ↓
Optimization Engine
       ↓
Candidate plans
       ↓
Agent negotiation
       ↓
Best plan
       ↓
Human approval
```

And the UI shows:

``` text
Original cost       ₹32,400
Optimized cost      ₹21,700
Saving              ₹10,700
Truck utilization   58% → 86%
Empty KM            412 → 190 km
SLA violations      0
```

Then the user asks:

> "What if the deadline changes?"

The system **actually recalculates**, rather than returning a
pre-written response.

That is the point at which FreightMesh becomes a convincing
**multi-agent hackathon project rather than an AI-themed logistics
dashboard**.
