import copy

def inject_location_context(td: dict, context:dict) -> dict:
    td["nearby"] = context
    return td

def convert_td(td:dict, context:list, contextIndex) -> list:
    td = copy.deepcopy(td)

    if "actions" in td:
        for action in td["actions"]:
            if "forms" in action:
                del action["forms"]

    if "events" in td:
        for event in td["events"]:
            if "forms" in event:
                del event["forms"]

    if "properties" in td:
        for prop in td["properties"]:
            if "forms" in prop:
                del prop["forms"]

    tds = []
    j = 0
    for i in context:
        contextTD = copy.deepcopy(td)
        contextTD["id"] = contextTD["id"] + "_" + str(j)
        contextTD = inject_location_context(contextTD, i)
        tds.append(contextTD)
        j += 1
    return tds

def convert_tds(tds:list, context:dict) -> list:
    tds_2 = []

    for td in tds:
        if td["id"] not in context:
            tds_2.append(td)
            continue

        c = context[td["id"]]["context"]
        tds_2 += convert_td(td, c, context[td["id"]]["index"])
    
    return tds_2

def convert_flow(flow: list[dict], context: dict):
    flow = copy.deepcopy(flow)
    for node in flow:
        if node["type"] in ["system-property-node", "system-action-node", "system-event-node"]:
            if node["thingID"] in context:
                node["thingID"] = node["thingID"] + "_" + str(context[node["thingID"]]["index"])

    return flow