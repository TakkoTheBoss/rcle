

<p align="center">
  <img src="c6-icon_v2.png" alt="C6 Logo" width="50%"/>
</p>

# Route-Lock Cellular Enforcement (RLCE)
**Version 1.0**  
Author: Michael "Mike" Curnow
Date: September 9 2025

---

## 1. Scope
This specification defines Route-Lock Cellular Enforcement (RLCE), a mechanism for constraining User Equipment (UE) to transmit data only over authorized cells that are valid along a pre-defined operational path. RLCE is designed for use in safety-critical and availability-sensitive domains including but not limited to:
- Public transit vehicles (buses, light rail, metro/subway)
- Freight rail
- Commercial fleet vehicles (trucks, tractor-trailers, delivery vans)
- Autonomous vehicles and robo-taxis (e.g., Waymo, Cruise)
- Any safety- or business-critical mobile system relying on cellular connectivity

![[Pasted image 20250910004956.png]]

***

## 2. Normative References
- 3GPP TS 36.331 (E-UTRA RRC)  
- 3GPP TS 38.331 (NR RRC)  
- IEC 62443 (Industrial communication networks — Security)  
- C6 Discipline v2.0 (Conduit & Zone Cyber-Physical Security)
- CENELEC TS 50701 (Railway applications \u2014 Cybersecurity)  

***

## 3. Terminology and Acronyms
- **ARFCN**: Absolute Radio Frequency Channel Number  
- **AS**: Access Stratum  
- **CAL**: Cell Access List (set of cells authorized for a segment)  
- **CBTC**: Communications-Based Train Control  
- **CellID**: Global Cell Identity (eNB/gNB ID + sector)  
- **EARFCN**: E-UTRA Absolute Radio Frequency Channel Number  
- **GNSS**: Global Navigation Satellite System  
- **Grace Window (g)**: Number of adjacent segments before and after the current one whose CAL entries are valid (typical g=1).  
- **Hysteresis (δ)**: A time threshold applied to segment determination to prevent rapid switching due to GNSS noise near boundaries.  
- **Legitimacy Check (L)**: Evaluation applied to a serving cell not in the CAL window, determining if it may be temporarily accepted.  
- **NAS**: Non-Access Stratum  
- **NSA**: Non-Standalone 5G  
- **NR-ARFCN**: New Radio Absolute Radio Frequency Channel Number  
- **OTA**: Over-The-Air (profile distribution and updates)  
- **PCI**: Physical Cell ID  
- **PDP**: Packet Data Protocol (session/context)  
- **PLMN**: Public Land Mobile Network (MCC+MNC)  
- **RAT**: Radio Access Technology (LTE, NR, etc.)  
- **RLCE**: Route-Lock Cellular Enforcement  
- **RSRP/RSRQ/SINR**: Standard LTE/NR RF metrics  
- **SA**: Standalone 5G  
- **SAIC**: Safety, Availability, Integrity, Confidentiality (security tetrad)  
- **Segmentation**: Division of an operational path into segments. In rail, this may correspond to fixed blocks or notional blocks in CBTC. In buses or fleets, it may be defined by distance (200–600 meters ≈ 650–2,000 feet) or logical regions (stops, intersections, depots).  
- **Segmentation Flapping**: Frequent oscillation of segment index due to small GNSS noise near boundaries.  
- **Segment**: A contiguous geographic or logical portion of an operational path, over which the set of observable valid cells is relatively stable.  
- **Traffic Enablement Function**: Decision logic that determines whether PDP contexts may be established and traffic forwarded, based on CAL membership and Legitimacy Check outcomes.  
- **TAC/TAI**: Tracking Area Code / Tracking Area Identity  
- **UE**: User Equipment  

***

## 4. RLCE in the Context of C6
RLCE is an instantiation of the C6 discipline (Conduit & Zone Cyber-Physical Security):

- In C6, a Conduit is any channel (physical, logical, broadcast, or cross-domain) that securely transfers data between zones or nodes. In modern mobility systems, the cellular network is the conduit linking vehicles to control centers and services.  
- RLCE transforms this conduit from a permissive channel into a verified conduit. By limiting connectivity to only those cells valid along an operational path, RLCE enforces C6’s mandate that conduits must be secure, bounded, and context-aware.  
- RLCE enforces the SAIC tetrad of C6:  
  - Safety: No safety-critical telemetry or commands traverse rogue cells.  
  - Availability: Service continuity is preserved via CAL windows and legitimacy checks.  
  - Integrity: The identity and behavior of each serving cell is validated.  
  - Confidentiality: Operational and passenger data only leave the vehicle via authorized conduits.  
- RLCE is domain-agnostic: applicable to buses, rail, AVs, freight, or any fleet, not just government-run systems.  

***

## 5. Functional Description

### 5.1 Route Profiles
- Each operational path SHALL be segmented.  
- For rail systems, segmentation MAY align with fixed blocks or notional blocks in CBTC.  
- For buses, fleets, or AVs, segmentation MAY be defined by geographic distance (200–600 meters ≈ 650–2,000 feet) or logical waypoints (stops, depots, intersections).  
- Every segment SHALL contain a Cell Access List (CAL) of valid cells.  
- Profiles SHALL be digitally signed and distributed OTA.

### 5.2 Route Indexing
At runtime, `pos(t)` (vehicle position at time *t*) SHALL be determined using GNSS/odometry and mapped to a segment index `seg(t)`.  
- Segmentation flapping SHALL be mitigated by hysteresis δ.

### 5.3 CAL Window
```
W(k) = ⋃_{i=k−g}^{k+g} CAL(i)
```
- *k*: current segment index  
- *g*: grace window  
- `⋃`: set union

### 5.4 Enforcement
At each poll interval Δt:  
1. Read serving cell `s(t)`.  
2. If `s(t) ∈ W(seg(t))` → allow traffic.  
3. Else → apply Legitimacy Check (Section 6).  

***

## 6. Legitimacy Check (Fail-Open Criteria)
A cell `s` MAY be temporarily accepted if all hold:  
1. **PLMN match**: `s.plmn ∈ P`  
2. **TAC continuity**: `|TAC(s) − TAC(prev)| ≤ Δ_TAC_max`  
3. **Frequency legitimacy**: `s.earfcn ∈ F` or `s.nr_arfcn ∈ F_NR`  
4. **RF envelopes**: `μ_X − σ_X ≤ X(s) ≤ μ_X + σ_X` for X ∈ {RSRP, RSRQ, SINR}  
5. **PCI sanity**: PCI must fit known reuse patterns  
6. **SIB sanity**: no barred state, valid PLMNs, qRxLevMin within −125 to −85 dBm  
7. **Security enforcement**: reject if integrity=EIA0 or cipher=EEA0  

```
L(s) = 1 if all conditions true
     = 0 otherwise
```

***

## 7. Decision Function
```
traffic_enabled(t) =
    1 if allowed(s(t), W(seg(t))) = 1
    1 if allowed(s(t), W(seg(t))) = 0 ∧ L(s(t)) = 1
    0 otherwise
```
- `∧` = logical AND  
- `∈` = element of  
- `μ_X` = mean of metric X  
- `σ_X` = standard deviation  

***

## 8. Mathematical Model
- Segment index: `seg(t) = f(pos(t), δ)`  
- Downtime bound: `Downtime ≤ Δt + T_reselect`  

Where:  
- `δ`: hysteresis threshold (s)  
- `Δt`: polling interval (s)  
- `T_reselect`: modem reselection latency (s)  

***

## 9. Pseudocode
```python
loop every Δt seconds:
    pos = read_gnss()
    seg = get_segment(pos, hysteresis=δ)
    window = cal_for(seg, grace=g)

    serving = modem.get_serving_cell()

    if serving in window:
        enable_traffic()
    elif legitimacy_checks(serving):
        enable_traffic()
        log_event("Fail-open acceptance", serving, pos, seg)
    else:
        disable_traffic()
        modem.deregister()
        modem.try_reselect(window)
```

***

## 10. Implementation Guidelines
- Δt MUST be 200–500 ms  
- g SHOULD be 1  
- Profiles MUST be signed  
- Vendor shims MUST expose: `lock_cell`, `set_bandmask`, `force_plmn`  
- State MUST persist after reset  

***

## 11. Security Properties (SAIC)
- **Safety**: Critical telemetry SHALL NOT traverse rogue cells  
- **Availability**: Service continuity maintained via CAL + legitimacy checks  
- **Integrity**: Serving cell identity and behavior validated continuously  
- **Confidentiality**: Data SHALL NOT traverse unauthorized conduits  

***

## 12. Operational Considerations
- Agencies or fleets MUST conduct RF surveys  
- OTA updates MUST be signed  
- Fail-open acceptances MUST be logged with full context  

***

## 13. Conformance
- **MUST**: block traffic on unauthorized cells, prevent PDP contexts, verify profiles  
- **SHOULD**: support dual-modem, log fail-open events tamper-evidently  
- **MAY**: allow fail-open for new but plausible cells, adaptive RF thresholds  

***

## 14. Worked Example
Segment CAL: EARFCN=900, PCI=123, TAC=8123  
Observed: EARFCN=900, PCI=321, TAC=8124, RSRP=−92  

- Not in CAL → `allowed=0`  
- All legitimacy checks pass → `L(s)=1`  
- Decision: traffic enabled, log event  

***

## 15. Conclusion
RLCE transforms cellular connectivity from a permissive assumption into a secure, bounded, and context-aware conduit. By integrating CALs, legitimacy checks, and SAIC enforcement, RLCE ensures that fleet and transit systems can trust their communications paths. The framework is domain-agnostic and ready for adoption across public and private mobility systems.  

***

## Changelog

| Date       | Version | Notes                                                                                                                                                      |
| ---------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2025-09-09 | 1.0     | Initial publication. Includes RLCE architecture, CALs, Legitimacy Checks, Decision Function, Pseudocode, SAIC properties, Conformance, and Worked Example. |

---

## Appendix A: Mathematical Reference

For convenience, all formulas are reproduced here.

**CAL Window**  
$$
W(k) = igcup_{i=k-g}^{k+g} CAL(i)
$$

**Legitimacy Function**  
$$
L(s) =
\begin{cases}
1 & \text{if all conditions (1–7) are true} \\
0 & \text{otherwise}
\end{cases}
$$  

**Traffic Enablement Function**  
$$
traffic\_enabled(t) =
\begin{cases}
1 & allowed(s(t), W(seg(t))) = 1 \\
1 & allowed(s(t), W(seg(t))) = 0 \land L(s(t)) = 1 \\
0 & \text{otherwise}
\end{cases}
$$  

**Segment Index Function**  
$$
seg(t) = f(pos(t), \delta)
$$  

**Downtime Bound**  
$$
Downtime \leq \Delta t + T_{reselect}
$$  

**RF Envelope Consistency**  
$$
\mu_X - \sigma_X \leq X(s) \leq \mu_X + \sigma_X
$$  

***

### Symbol Legend
- $s(t)$ = serving cell observation at time $t$  
- $W(k)$ = CAL window for segment $k$  
- $\Delta t$ = polling interval (s)  
- $T_{reselect}$ = modem reselection/reattach latency (s)  
- $\delta$ = hysteresis threshold (s)  
- $\mu_X$ = mean of RF metric $X$  
- $\sigma_X$ = standard deviation of $X$  
- $\land$ = logical AND  
- $\in$ = “element of”  
- $\cup$ = union of sets  
- $|x|$ = absolute value  
