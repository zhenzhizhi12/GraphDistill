"""Debug script to inspect graph structure around TimeZone."""
import json
from graph_builder import GraphBuilder

gb = GraphBuilder.load_json("test_graph_with_vectors.json")
g = gb.graph

nid = "class:std_time_timezone"
print("=== Node:", nid, "===")
data = g.nodes.get(nid, {})
print("name:", data.get("name"))
print("type:", data.get("entity_type"))
print("content[:200]:", (data.get("content") or "")[:200])

print("\n--- Out edges ---")
for _, t, d in g.out_edges(nid, data=True):
    rt = d.get("relation_type", "")
    print(f"  -> {t}  [{rt}]")

print("\n--- In edges ---")
for s, _, d in g.in_edges(nid, data=True):
    rt = d.get("relation_type", "")
    print(f"  {s} ->  [{rt}]")

# Check what concept:time has
print("\n=== Node: concept:time ===")
cdata = g.nodes.get("concept:time", {})
print("name:", cdata.get("name"))
print("type:", cdata.get("entity_type"))

print("\n--- Out edges (DOCUMENTED_AT only) ---")
for _, t, d in g.out_edges("concept:time", data=True):
    if d.get("relation_type") == "DOCUMENTED_AT":
        tdata = g.nodes.get(t, {})
        print(f"  -> {t}  name={tdata.get('name')}")

# Check BELONGS_TO chain from class:std_time_timezone
print("\n--- BELONGS_TO chain from class:std_time_timezone ---")
for _, t, d in g.out_edges(nid, data=True):
    if d.get("relation_type") == "BELONGS_TO":
        print(f"  Level 1: -> {t}")
        for _, t2, d2 in g.out_edges(t, data=True):
            if d2.get("relation_type") == "DOCUMENTED_AT":
                t2data = g.nodes.get(t2, {})
                print(f"    DOCUMENTED_AT -> {t2}  name={t2data.get('name')}")
            if d2.get("relation_type") == "BELONGS_TO":
                print(f"    Level 2 BELONGS_TO: -> {t2}")
                for _, t3, d3 in g.out_edges(t2, data=True):
                    if d3.get("relation_type") == "DOCUMENTED_AT":
                        t3data = g.nodes.get(t3, {})
                        print(f"      DOCUMENTED_AT -> {t3}  name={t3data.get('name')}")

# Also check if there's a concept:timezone
print("\n=== Searching for timezone-related entities ===")
for node_id, node_data in g.nodes(data=True):
    name = (node_data.get("name") or "").lower()
    if "timezone" in node_id.lower() or "timezone" in name:
        etype = node_data.get("entity_type", "")
        print(f"  {node_id} (type={etype}, name={node_data.get('name')})")
        # Check its BELONGS_TO
        for _, t, d in g.out_edges(node_id, data=True):
            rt = d.get("relation_type", "")
            if rt in ("BELONGS_TO", "DOCUMENTED_AT"):
                print(f"    -> {t} [{rt}]")

# Check what file entities contain "time_package"
print("\n=== File entities with 'time' in name ===")
for node_id, node_data in g.nodes(data=True):
    if node_data.get("entity_type") == "File" and "time" in (node_data.get("name") or "").lower():
        print(f"  {node_id}  name={node_data.get('name')}")
        # Who points to this file?
        for s, _, d in g.in_edges(node_id, data=True):
            if d.get("relation_type") == "DOCUMENTED_AT":
                print(f"    <- {s} [DOCUMENTED_AT]")
