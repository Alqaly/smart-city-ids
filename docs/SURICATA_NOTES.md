# Suricata Implementation Notes

## Current Status

Suricata has been configured as a **primary IDS system** alongside Falco, providing network-level threat detection.

### Why Suricata Was Initially Broken

1. **Missing Kubernetes Configuration**
   - Original manifest didn't include proper security context
   - No NET_ADMIN or NET_RAW capabilities
   - Missing hostNetwork configuration

2. **Network Interface Detection Issues**
   - Kubernetes pods don't have direct access to host network interfaces by default
   - Suricata needs `af-packet` or `pcap` mode to function
   - Container environment (loopback only) limited Suricata's capabilities

3. **Configuration Incompatibilities**
   - Original af-packet config assumed full host network access
   - Fallback modes weren't properly configured
   - No error handling for missing interfaces

## Why Both IDS Systems Matter

**Falco + Suricata form a defense-in-depth strategy:**

- **Falco**: Monitors what containers DO (syscalls, processes, file access)
- **Suricata**: Monitors what's SENT OVER THE NETWORK (traffic patterns, protocols)

Neither alone is sufficient. Falco misses network-layer attacks; Suricata misses internal container behavior.

## Deployment Architecture

In your setup:

```
Internet/Network
       ↓
   [Suricata monitors network traffic]
       ↓
  Kubernetes Cluster
       ↓
   [Containers running]
       ↓
   [Falco monitors syscalls]
       ↓
    IDS API
       ↓
  LLM Analysis + Automated Response
```

## Implementation Challenges in Kubernetes

Suricata in Kubernetes faces challenges that make it complex:

1. **Network Isolation**: K8s abstracts away host network details
2. **Privilege Requirements**: Packet capture needs elevated privileges
3. **Performance**: Monitoring all traffic impacts resource usage
4. **Configuration**: af-packet mode needs specific kernel features

## Recommended Solution (Not Yet Implemented)

For production deployment, consider:

1. **Daemonset on Host Nodes**: Run Suricata on host network (more privileged)
2. **Sidecar Pattern**: Run network monitor as sidecar with pods that need deep inspection
3. **eBPF-based Approach**: Use eBPF for network monitoring (like Cilium) instead of Suricata
4. **External IDS**: Deploy Suricata outside cluster, monitoring traffic to/from cluster

## Falco is the Primary Runtime IDS

Currently, **Falco is fully operational** for runtime security monitoring:
- ✅ Monitoring all container syscalls
- ✅ Detecting suspicious behavior
- ✅ Sending alerts to IDS API
- ✅ Integrated with LLM analysis

This provides comprehensive runtime threat detection while Suricata implementation is refined.

## Future Work

- [ ] Implement Suricata as eBPF-based network monitor
- [ ] Add Cilium NetworkPolicy with L7 visibility
- [ ] Deploy traffic capture on external gateway
- [ ] Implement sidecar-based network inspection for critical pods

---

**Current Assessment:**
- Falco: ✅ Fully operational (primary runtime IDS)
- Suricata: 🔄 Requires Kubernetes-native network monitoring approach
