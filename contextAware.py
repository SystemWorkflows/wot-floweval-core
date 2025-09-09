import copy

def inject_location_context(td: dict, context:dict) -> dict:
    td["nearby"] = context
    return td

def convert_td(td:dict, context:list, contextIndex) -> list:
    tds = []
    j = 0

    for i in context:
        tds.append(copy.deepcopy(td))

        if contextIndex != j:
            tds[-1]["id"] = tds[-1]["id"] + "_" + str(j)

        tds[-1] = inject_location_context(tds[-1], i)
        j += 1
    
    for i in range(len(tds)):
        if i == contextIndex:
            continue

        if "actions" in tds[i]:
            for action in tds[i]["actions"]:
                if "forms" in action:
                    for form in action["forms"]:
                        form["href"] = ""
        
        if "events" in tds[i]:
            for event in tds[i]["events"]:
                if "forms" in event:
                    for form in event["forms"]:
                        form["href"] = ""
        
        if "properties" in tds[i]:
            for prop in tds[i]["properties"]:
                if "forms" in prop:
                    for form in prop["forms"]:
                        form["href"] = ""
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