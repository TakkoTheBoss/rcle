# Route-Lock Cellular Enforcement (RLCE)

<p align="center">
  <img src="c6-icon_v2.png" alt="C6 Logo" width="40%"/>
</p>

## Overview
Route-Lock Cellular Enforcement (RLCE) is a specification for constraining cellular connectivity in safety-critical and availability-sensitive mobile environments.  
It ensures that vehicles and fleet systems only connect to authorized cellular cells along pre-defined operational paths.

RLCE applies to:
- Public transit vehicles (bus, light rail, subway)
- Freight rail and CBTC rail systems
- Commercial fleet (trucks, delivery vans, logistics)
- Autonomous vehicles and robo-taxis
- Any mobile system relying on cellular for safety or operations

RLCE is developed in alignment with the **C6 Discipline** and enforces the **SAIC tetrad**:
- **Safety**
- **Availability**
- **Integrity**
- **Confidentiality**

## Key Features
- **Cell Access Lists (CALs):** Define the valid cells per route segment  
- **Legitimacy Checks (L):** Allow continuity on new but valid cells while blocking rogues  
- **Decision Function:** Fail-closed traffic gating for PDP contexts  
- **SAIC Enforcement:** Conduits treated as first-class security objects  
- **Domain Agnostic:** Rail, bus, AVs, fleets — public or private  

## Documentation
The full technical specification is maintained in this repository:

[`Latest RCLE Spec`](.versions/1.0/rcle_1.md)

This includes:
- Functional description
- Mathematical model
- Pseudocode
- Implementation guidelines
- Conformance criteria
- Worked examples
- Appendix with all math in one place

## License
This project is released under the **MIT License**.  
See [LICENSE](./LICENSE) for details.

---

> Author: Michael "Mike" Curnow  
> Date: September 9, 2025

