# Smart Crypto Mining Feasibility

Updated: 2026-07-05

Status: speculative research only. Do not buy hardware, run miners, or commit power usage without a separate approval.

## Thesis

Mining is not a software edge by itself. Expected revenue is mostly driven by hashrate share, coin price, block reward, network difficulty, pool fees, hardware efficiency, and electricity cost. A "smart" layer can help avoid bad decisions by monitoring profitability, switching only where supported, forecasting breakeven, and pausing when power economics are negative. It cannot make weak hardware profitable.

## Opportunity Shape

| Field | Current view |
| --- | --- |
| Target customer | Internal JVT experiment first; possibly homelab operators or small offices only if a monitor proves useful. |
| Pain | People buy mining hardware from hype without accounting for electricity, heat, noise, difficulty, tax, and hardware payback. |
| Offer | A mining feasibility dashboard: hardware watchlist, power-rate calculator, profitability feed, breakeven/payback model, and alerts. |
| Pricing hypothesis | Internal only for now. If productized: $99 setup + $10-$25/mo monitor for hobbyists, or custom for small operators. |
| Delivery complexity | Medium for dashboard and alerts; high for actual mining operations, hardware, power, cooling, and uptime. |
| Risks | Poor profitability, volatile coin prices, rising difficulty, heat/noise, hardware depreciation, power cost, tax/reporting complexity, scams, custody/security. |
| Next validation step | Build a read-only calculator using current hardware, local power assumptions, and live profitability sources. Approve hardware only if modeled payback is conservative and under 12-18 months. |

## Current Practical Conclusion

- Do not mine Bitcoin on general-purpose GPUs or Apple Silicon. Bitcoin mining is ASIC-dominated.
- Do not mine Ethereum mainnet; Ethereum no longer uses proof-of-work.
- GPU/CPU mining may be useful as a learning lab, but likely not a serious path to the March 2027 revenue target unless electricity is very cheap and hardware is already owned.
- The better near-term use of JVT compute is local AI demos, voice intake, document automation, lead research, and monitoring.
- The useful build is a profitability monitor and hardware decision gate, not a miner.

## 2026-07-05 Refresh

Current operating decision:

- Keep crypto/mining in the research-lab lane only.
- Build or maintain a read-only feasibility monitor before considering hardware.
- Required monitor inputs: hardware model, hashrate, power draw, local electricity cost, pool fee, coin/network difficulty, coin price, estimated heat/noise burden, and payback window.
- Approval gate: do not buy ASICs/GPUs, create wallets, mine, stake, custody funds, or join pools unless the operator approves a separate hardware, power, custody, and tax/reporting plan.
- M4 note: live profitability pulls and paper-trader refreshes are blocked while the M4 reports `Errno 49` / TCP socket exhaustion. Do not treat failed refreshes during that state as a strategy failure.

Validation checklist before any spend:

1. Run the monitor with conservative electricity and fee assumptions.
2. Require a modeled payback under 12-18 months after hardware depreciation.
3. Confirm the hardware can run without unacceptable noise, heat, or uptime burden.
4. Compare against the opportunity cost of using the same compute budget for JVT service delivery.

## Sources To Track

- Ethereum proof-of-work deprecation: https://ethereum.org/developers/docs/consensus-mechanisms/pow/
- Cambridge Bitcoin Electricity Consumption Index methodology: https://ccaf.io/cbnsi/cbeci/methodology
- Hashrate Index mining economics and hashprice updates: https://hashrateindex.com/blog/
- CoinCalculators live profitability model: https://coincalculators.io/
