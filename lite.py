### conversion from full bodied formats to lite formats and vice versa
import traceback
import json
import copy
from src.thingDescriptionCollection import ThingDescriptionCollection

def convert_td_genLite(td:dict) -> dict:
    if "security" in td:
        del td["security"]

    if "securityDefinitions" in td:
        del td["securityDefinitions"]

    if "forms" in td:
        del td["forms"]

    if "uriVariables" in td:
        del td["uriVariables"]

    if "@context" in td:
        del td["@context"]

    if "@type" in td:
        del td["@type"]

    if "properties" in td:
        for i in td["properties"]:
            if "forms" in td["properties"][i]:
                del td["properties"][i]["forms"]

    if "actions" in td:
        for i in td["actions"]:
            if "forms" in td["actions"][i]:
                del td["actions"][i]["forms"]

    if "events" in td:
        for i in td["events"]:
            if "forms" in td["events"][i]:
                del td["events"][i]["forms"]

    del_list = []
    for k, v in td.items():
        if (v == "") or (v == {}) or (v == []):
            del_list.append(k)

    for i in del_list:
        del td[i]

    return td

def convert_tds_genLite(tds:list) -> list:
    for td in tds:
        td = convert_td_genLite(td)

    return tds


def getID(tds, type, name):
    for td in tds:
        if (type in td) and (name in td[type]):
            return td["id"]
    
    return None

def convert_flow_lite(flow:list,tds:dict) -> list:
    for node in flow:
        if "name" in node:
            del node["name"]
        if "x" in node:
            del node["x"]
        if "y" in node:
            del node["y"]
        if "z" in node:
            del node["z"]
        if "disabled" in node:
            del node["disabled"]
        if "redeploy" in node:
            del node["redeploy"]
        if "thingDirectoryURI" in node:
            del node["thingDirectoryURI"]
        if node["type"] == "system-event-node":
            node["type"] = "sys-evt"
            node["thingID"] = getID(tds, "events", node["thingEvent"])
            del node["thingEventValue"]
        if node["type"] == "system-property-node":
            node["type"] = "sys-prp"
            node["thingID"] = getID(tds, "properties", node["thingProperty"])
            del node["thingPropertyValue"]
        if node["type"] == "system-action-node":
            node["type"] = "sys-act"
            node["thingID"] = getID(tds, "actions", node["thingAction"])
            del node["thingActionValue"]

    for node in flow:
        if node["type"] == "tab":
            flow.remove(node)
            break

    return flow


def convert_flow_full(flow:list, tds:dict, tddURI) -> list:
    tdc = ThingDescriptionCollection(tds=tds)

    try:
        for node in flow:
            node["z"] = "test flow"

            match node["type"]:
                case "sys-evt":
                    node["type"] = "system-event-node"
                    node["thingDirectoryURI"] = tddURI
                    event = tdc.selectElement("events", node["thingEvent"], id=node["thingID"])
                    description = ""

                    if "description" in event:
                        description = event["description"]
                    
                    node["thingEventValue"] = json.dumps({
                        "uri": tddURI + "/things/" + node["thingID"],
                        "output": event["data"],
                        "description": description,
                        "event": node["thingEvent"]
                    })

                case "sys-prp":
                    node["type"] = "system-property-node"
                    node["thingDirectoryURI"] = tddURI

                    prop = tdc.selectElement("properties", node["thingProperty"], id=node["thingID"])
                    description = ""

                    if "description" in prop:
                        description = prop["description"]

                    node["thingPropertyValue"]= json.dumps({
                        "uri": prop["forms"][0]["href"],
                        "type": prop["type"],
                        "description": description,
                        "property": node["thingProperty"]
                    })

                case "sys-act":
                    node["type"] = "system-action-node"
                    node["thingDirectoryURI"] = tddURI

                    action = copy.deepcopy(tdc.selectElement("actions", node["thingAction"], id=node["thingID"]))
                    description = ""

                    if "description" in action:
                        description = action["description"]

                    output = {}
                    if "output" in action:
                        output = action["output"]

                    params = {}
                    if "input" in action:
                        params = action["input"]
                        if params["type"] == "object":
                            params = params["properties"]
                            for k, v in params.items():
                                params[k] = v["type"]
                    
                    node["thingActionValue"] = json.dumps({
                        "uri": action["forms"][0]["href"],
                        "params": params,
                        "output": output,
                        "description": description,
                        "action": node["thingAction"]
                    })

        flow.append({"type":"tab","label":"Flow 1","id":"test flow"})
        return flow
    except Exception as e:
        print(e)
        traceback.print_exception(type(e), e, e.__traceback__)
        print("Error in converting flow")
        raise Exception("failed to convert flow to full format, check all variables are correct.")
