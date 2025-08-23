import copy
import json
import ast
import copy
import traceback
from typing import Any, Tuple
from src.helpers import flatten

class NodeFactory:
    @staticmethod
    def produceNode(name:str, parameters:Tuple[Any]):
        match name:
            case "system-action-node":      return SystemActionNode(*parameters)
            case "system-property-node":    return SystemPropertyNode(*parameters)
            case "change":                  return ChangeNode(*parameters)
            case "switch":                  return SwitchNode(*parameters)
            case _:                         return PassThroughNode(*parameters)

class Node:
    node = None
    state = {}
    children = []
    
    def __init__(self, node, flow, tds):
        self.node = node
        self.flow = flow
        self.tds = tds
        self.state = {}
        self.conditions = []
        self.interactions = []
        self.children = []
        self.errors = { self.node["id"] : [] }

    def addChild(self, child):
        self.children.append(child)

    def addChildren(self):
        for wire in flatten(self.node["wires"]):
            state, conditions, interactions = copy.deepcopy((self.state, self.conditions, self.interactions))
            receiverType = self.flow[wire]["type"]

            child = NodeFactory.produceNode(receiverType, (self.flow[wire], self.flow, self.tds, state, conditions, interactions))

            self.addChild(child)
            self.errors = self.errors | child.getErrors()
            # get errors from child

    def getChildren(self):
        """
        todo: currently causing crash - fix
        """
        #print(self.node["type"])
        c = copy.deepcopy(self.children)
        for i in self.children:
            c += i.getChildren()
        return c

    def getErrors(self):
        return self.errors
    
    def match(self, subflow_matches):
        return []
    
    def extractConditions(self):
        conditions = []
        for i in self.children:
            conditions += i.extractConditions()
        return conditions

#%% Secondary Nodes
class SecondaryNode(Node):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds)
        self.incomingState = incomingState
        self.state = copy.deepcopy(incomingState)
        self.incomingConditions = incomingConditions
        self.conditions = copy.deepcopy(incomingConditions)
        self.previousInteractions = previousInteractions
        self.interactions = copy.deepcopy(previousInteractions)
        #print("incoming state @" +node["type"] +  ": " + json.dumps(self.incomingState))
        #print("incoming conditions @" +node["type"] +  ": " + json.dumps(self.incomingConditions))

class ChangeNode(SecondaryNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)
        
        self.updateState()
        self.addChildren()
    
    def updateState(self):
        def stateLookup(path):
            search = path.split(".")
            if search[0] == "msg":
                search = search[1:]
            data = copy.deepcopy(self.state)#changed from incomingState to allow changes from previous rules to be reflected
            #print(search)
            #print(data)
            try:
                for j in search[:-1]:
                    data = data[j]
                    if data["type"] == "object":
                        data = data["properties"]
                data = data[search[-1]]
                return data
            except Exception as e:
                self.errors[self.node["id"]].append("Error in change node state lookup: " + str(e))
                raise e

        print("change Node incoming state: ", self.state)
        rules = self.node["rules"]
        print("change Node rules: ", rules)
        for i in rules:
            try:
                if i["tot"] == "jsonata":
                    print(i["to"])
                    if i["to"][0] == "{":# jsonata
                        x = i["to"][1:-1]
                        y = x.replace(" ", "")
                        parts = y.split(',"')
                        if len(parts) > 1:
                            for x in range(1,len(parts)):
                                parts[x] = '"' + parts[x]
                        print("parts: ", parts)
                        output = {}
                        for j in range(0,len(parts)):
                            parts[j] = parts[j].split(":",1)
                            print(parts)
                            typ = self.__check_type(parts[j][1])
                            source = {"type": "change", "id": self.node["id"]}
                            if typ == "lookUp":
                                output[parts[j][0][1:-1]] = stateLookup(parts[j][1])
                            elif typ == int:
                                output[parts[j][0][1:-1]] = {"type": "integer", "source": source}
                            elif typ == float:
                                output[parts[j][0][1:-1]] = {"type": "number", "source": source}
                            elif typ == str:
                                output[parts[j][0][1:-1]] = {"type": "string", "source": source}
                            elif typ == bool:
                                output[parts[j][0][1:-1]] = {"type": "boolean", "source": source}
                            elif typ == 'typeError':
                                #components = parts[j][1].split("+")
                                #contents = []
                                #for k in components:
                                #    if self.__check_type(k) == "lookUp":
                                #        contents.append(stateLookup(k))
                                #output[parts[j][0][1:-1]] = {"type": "string", "source": source, "contains": contents}
                                output[parts[j][0][1:-1]] = {"type": "string", "source": source}
                                #print(parts[j][1])
                                
                        self.state[i["p"]]={"type": "object"}
                        self.state[i["p"]]["properties"] = output
                    else:
                        typ = self.__check_type(i["to"])
                        source = {"type": "change", "id": self.node["id"]}
                        if typ == "lookUp":
                            self.state[i["p"]] = stateLookup(i["to"])
                        elif typ == int:
                            self.state[i["p"]] = {"type": "integer", "source": source}
                        elif typ == float:
                            self.state[i["p"]] = {"type": "number", "source": source}
                        elif typ == str:
                            self.state[i["p"]] = {"type": "string", "source": source}
                        elif typ == bool:
                            self.state[i["p"]] = {"type": "boolean", "source": source}
                        elif typ == 'typeError':
                            self.state[i["p"]] = {"type": "string", "source": source}
                            #print(parts[j][1])

                if i["tot"] == "msg":# check this
                    lu = stateLookup(i["to"])
                    p = i["p"].split(".")
                    data = self.state

                    for j in p[:-1]:
                        data = data[j]
                        if data["type"] == "object":
                            data = data["properties"]

                    data[p[-1]] = lu


                source = {"type": "change", "id": self.node["id"]}
                if i["tot"] == "str":
                    self.state[i["p"]] = {"type": "string", "source": source}
                if i["tot"] == "num":
                    self.state[i["p"]] = {"type": "number", "source": source}
                if i["tot"] == "bool":
                    self.state[i["p"]] = {"type": "boolean", "source": source}
                if i["tot"] == "json":
                    self.state[i["p"]] = {"type": "object"}
                    p = {}
                    for k,v in json.loads(i["to"]).items():
                        typ = self._self.__check_type(v)
                        if typ == int:
                            p[k] = {"type": "integer", "source": source}
                        elif typ == float:
                            p[k] = {"type": "number", "source": source}
                        elif typ == str:
                            p[k] = {"type": "string", "source": source}
                        elif typ == bool:
                            p[k] = {"type": "boolean", "source": source}                
                    self.state[i["p"]]["properties"] = p
            except Exception as e:# do something here
                print("Error in change node: ", e)
                print(traceback.format_exc())
        print("change node state: ", self.state)
    
    def __check_type(self, value):
        if value.startswith('msg.') or ('payload.' in value and not value.startswith('"')):
            return 'lookUp'
        try:
            evaluated_value = ast.literal_eval(value)
            return type(evaluated_value)
        except (ValueError, SyntaxError):
            return 'typeError'

class InteractionNode(SecondaryNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions=[], previousInteractions=[]):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)
        self.validatePayload()
        self.updateState()
        self.interactions.append(self)
        self.addChildren()

    def updateState(self):
        pass

    def validatePayload(self):
        pass

class PassThroughNode(SecondaryNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)
        self.state = self.incomingState
        self.addChildren()

class SwitchNode(SecondaryNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)
        self.updateConditions()
        self.addChildren()

    def updateConditions(self):
        def stateLookup(path):
            search = path.split(".")
            if search[0] == "msg":
                search = search[1:]
            data = copy.deepcopy(self.incomingState)
            for j in search:
                data = data[j]
                if data["type"] == "object":
                    data = data["properties"]
            return data
        
        print("switch Node: ", self.node)
        print("incoming state: ", self.incomingState)
        rules = self.node["rules"]
        try:
            property = stateLookup(self.node["property"])
        except Exception as e:
            print("Error in switch node: ", e)
            print(traceback.format_exc())
            property = {}
        for i in rules:
            i["property"] = property
        print("rules: ", self.node["rules"])

    def addChildren(self):
        print(self.node["wires"])
        print(self.node["rules"])

        if len(self.node["wires"]) != len(self.node["rules"]):
            return
        
        for n in range(0, len(self.node["wires"])):
            for j in self.node["wires"][n]: 
                nodeType = self.flow[j]["type"]

                state, conditions, interactions = copy.deepcopy((
                    self.state,
                    self.incomingConditions + [self.node["rules"][n]],
                    self.interactions
                ))

                child = NodeFactory.produceNode(nodeType, (self.flow[j], self.flow, self.tds, state, conditions, interactions))

                self.addChild(child)
                self.errors = self.errors | child.getErrors()

#%% System-Nodes
class SystemActionNode(InteractionNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)

    def extractConditions(self):
        conditions = super().extractConditions()
        #print(conditions)
        #print("cond: " + json.dumps(conditions))
        input = self.incomingState["payload"]
        if "properties" in input:# removes the id as is unnecesary
            for i in input["properties"].values():
                if "source" in i:
                    if "id" in i["source"]:
                        del i["source"]["id"]
                    if "prev" in i["source"]:
                        del i["source"]["prev"]

        pre_nodes = []
        for i in self.previousInteractions:
            if i.node["type"] == "system-action-node":
                prev = i.node["thingAction"]
                print(prev)
                pre_nodes.append(prev)
            if i.node["type"] == "system-property-node":
                if i.node["mode"] == "write":
                    prev = i.node["thingProperty"]
                    print(prev)
                    pre_nodes.append(prev)

        
        c = [self.node["thingAction"], {"pre_nodes": pre_nodes, "conditions": self.conditions, "input": input}]
        
        conditions.append(c)
        return conditions

    def validatePayload(self):
        if self.incomingState["payload"] == {}:
            return False
        actionInput = self.tds.getActionInput(self.node["thingAction"])
        print(self.node["thingAction"])
        print("action input: ", actionInput)
        payload = copy.deepcopy(self.incomingState["payload"])
        print("incoming state: ", self.incomingState)
        if payload["type"] != "object":
            if payload["type"] == actionInput["type"]:
                return True
            else:
                self.errors[self.node["id"]].append("expected: " + json.dumps(actionInput) + " got: " + json.dumps(payload))
                return False
        else:
            incProp = {}
            for k,v in payload["properties"].items():
                incProp[k] = v["type"]
            actInProp = {}
            for k,v in actionInput["properties"].items():
                actInProp[k] = v["type"]
            if sorted(incProp) == sorted(actInProp):
                return True
            else:
                self.errors[self.node["id"]].append("expected: " + json.dumps(actionInput) + " got: " + json.dumps(payload))
                return False

            
    
    def updateState(self):
        if self.node["outputToMsg"]:
            output = self.tds.getActionOutput(self.node["thingAction"])
            print(output)
            if output != None:
                prev = []
                for i in self.previousInteractions:
                    if i.node["type"] == "system-action-node":
                        prev.append(i.node["thingAction"])
                    if i.node["type"] == "system-property-node":
                        if i.node["mode"] == "write":
                            prev.append(i.node["thingProperty"])
                source = {"type":"action", "name": self.node["thingAction"], "id": self.node["id"], "prev": prev}#replace id with generic counter
                if output["type"] != "object":
                    output["source"] = source
                else:
                    for k,v in output["properties"].items():
                        v["source"] = source
                self.state["payload"] = output
            else:
                self.state["payload"] = {}
        else:
            self.state = self.incomingState
        print("outgoing: ", self.state)

    def conditionsMatch(self, conditions):
        print("self conditions: " + json.dumps(self.conditions))
        print("conditions: " + json.dumps(conditions))
        for i in conditions:
            if "property" in i:
                if "source" in i["property"]:
                    if "id" in i["property"]["source"]:
                        del i["property"]["source"]["id"]# remove id from source

                    if "prev" in i["property"]["source"]:
                        del i["property"]["source"]["prev"]# remove prev from source
        for i in self.conditions:
            if "property" in i:
                if "source" in i["property"]:
                    if "id" in i["property"]["source"]:
                        del i["property"]["source"]["id"]# remove id from source
                    
                    if "prev" in i["property"]["source"]:
                        del i["property"]["source"]["prev"]# remove prev from source

        if conditions == self.conditions:
            return True

    def inputMatch(self, input):

        if not self.validatePayload():
            return False
        else:
            print("payload: ", self.incomingState["payload"])
            if input["type"]!= "object" and self.incomingState["payload"]["type"] != "object":
                if "source" in input:
                    i_source = input["source"]
                    p_source = self.incomingState["payload"]["source"]
                    if i_source["type"] == p_source["type"]:
                        if i_source["type"] == "event":
                            return True
                        if "name" in i_source:
                            if i_source["name"] == p_source["name"]:
                                if "pos" in i_source:
                                    if i_source["pos"]["location"] == "last":
                                        node = i_source["pos"]["node"]
                                        x = self.previousInteractions[len(p_source["prev"])+1:]
                                        return node not in x

                                    if i_source["pos"]["location"] == "after":
                                        node = i_source["pos"]["node"]
                                        return node in p_source["prev"]

                                else:
                                    return True
                            else:
                                return False
                        else:
                            return True
                else:
                    return True
            elif input["type"] == "object" and self.incomingState["payload"]["type"] == "object":
                for k,v in input["properties"].items():
                    if k not in self.incomingState["payload"]["properties"]:
                        return False
                    if "source" in v:
                        i_source = v["source"]
                        print("incoming state: ", self.incomingState["payload"])
                        p_source = self.incomingState["payload"]["properties"][k]["source"]
                        if i_source["type"] == p_source["type"]:# does this need a closing else?
                            if i_source["type"] == "event":
                                return True
                            if "name" in i_source:
                                if i_source["name"] == p_source["name"]:
                                    if "pos" in i_source:
                                        if i_source["pos"] == "last":#finish this
                                            for i in reversed(self.previousInteractions):
                                                name = None
                                                if i.node["type"] == "system-action-node":
                                                    name = i.node["thingAction"]
                                                if  i.node["type"] == "system-property-node":
                                                    name = i.node["thingProperty"]
                                                if name == input["name"]:
                                                    if p_source["id"] == i.node["id"]:
                                                        return True
                                                    else:
                                                        return False
                                    else:
                                        return True
                                else:
                                    return True
                            else:
                                return True
                    else:
                        return True
            return False


    def preConditionsMatch(self, pre_nodes):
        if pre_nodes == []:
            return True
        else:
            prev=[]
            for i in self.previousInteractions:#add filtering to exclude irrelevant interactions when selecting which interactions to check
                print(i.node["type"])
                if i.node["type"] == "system-action-node":
                    print("action: " + i.node["thingAction"])
                    prev.append(i.node["thingAction"])
                if i.node["type"] == "system-property-node":
                    if i.node["mode"] == "write":
                        prev.append(i.node["thingProperty"])
            print("prev: " + str(prev))
            if pre_nodes == prev:
                return True
            else:
                return False
    
    def match(self, subflow_matches):
        print("subflow matches: ", subflow_matches)
        # print node details for match types
        
        candidates = []
        print("thingAction: " + self.node["thingAction"])
        for i in subflow_matches:
            if i[0] == self.node["thingAction"]:
                candidates.append(i)
        print("candidates: ", candidates)
        match ={"preConditionMatch": False, "conditionsMatch": False, "inputMatch": False}
        candidates = [x for x in candidates if self.preConditionsMatch(x[1]["pre_nodes"])]
        if candidates != []:
            match["preConditionMatch"] = True
            candidates = [x for x in candidates if self.conditionsMatch(x[1]["conditions"])]
            if candidates != []:
                match["conditionsMatch"] = True
                candidates = [x for x in candidates if self.inputMatch(x[1]["input"])]
                if candidates != []:
                    match["inputMatch"] = True

        for i in candidates:#should be no more than one candidate but just in case checks list, this check prevents multiple nodes matching against the same case.
            subflow_matches.remove(i)

        status = match["preConditionMatch"] and match["conditionsMatch"] and match["inputMatch"]
        print("final Candidates: " + json.dumps(candidates))
        return {"status": status, "name": self.node["thingAction"], "match": match, "candidates": candidates}# needs reversing to check flow validity

class SystemEventNode(Node):
    def __init__(self, node, flow, tds):
        super().__init__(node, flow, tds)
        print("SystemEventNode: " + json.dumps(node["thingEvent"]))
        self.extractState()
        self.addChildren()
    
    def extractState(self):
        eventData = self.tds.getEventData(self.node["thingEvent"])
        self.state["payload"] = eventData
        if self.state["payload"] != None:
            if self.state["payload"]["type"] == "object":
                for i in self.state["payload"]["properties"].values():
                    i["source"] = {"type":"event", "name": self.node["thingEvent"], "id": self.node["id"]}
            else:
                self.state["payload"]["source"] = {"type":"event", "name": self.node["thingEvent"], "id": self.node["id"]}

    def match(self, subflow_matches):
        children = self.getChildren()
        matches = {}
        for i in children:
            if i.node["type"] == "system-action-node" or (i.node["type"] == "system-property-node" and i.node["mode"] == "write"):
                matches[i.node["id"]] = i.match(subflow_matches)
        #print("matches: " + json.dumps(matches))
        left_over = copy.deepcopy(subflow_matches)
        #adjust scores for left over cases- e.g. not enough nodes in real flow compared to true flow
        return {"matches": matches, "left_over": left_over}

    # def extractConditions(self):
    #     conditions = []
    #     for i in self.getChildren():
    #         conditions += i.extractConditions()
    #     return conditions

class SystemPropertyNode(InteractionNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)

    
    def updateState(self):
        if self.node["mode"] == "read":
            output = self.tds.getPropertyValue(self.node["thingProperty"])
            prev = []
            for i in self.previousInteractions:
                if i.node["type"] == "system-action-node":
                    prev.append(i.node["thingAction"])
                if i.node["type"] == "system-property-node":
                    if i.node["mode"] == "write":
                        prev.append(i.node["thingProperty"])
            source = {"type":"property", "name": self.node["thingProperty"], "id": self.node["id"], "prev": prev}
            if output["type"] != "object":
                output["source"] = source
            else:
                for k,v in output["properties"].items():
                    v["source"] = source
            self.state["payload"] = output
        else:
            self.state = self.incomingState

    def validatePayload(self):
        if self.node["mode"] == "write":
            if self.state["payload"] == {}:
                return False
            propertyInput = self.tds.getPropertyValue(self.node["thingProperty"])
            payload = self.state["payload"]
            #print(self.state)
            if payload["type"] != "object":
                if "source" in payload:
                    del payload["source"]
            else:
                for k,v in payload["properties"].items():
                    if "source" in v:
                        del v["source"]
            if sorted(payload) == sorted(propertyInput):
                return True
            else:
                self.errors[self.node["id"]].append("expected: " + json.dumps(propertyInput) + " got: " + json.dumps(payload))
            return False
        else:
            return True
        


    def conditionsMatch(self, conditions):
        if conditions == self.conditions:
            return True

    def inputMatch(self, input):

        if not self.validatePayload():
            return False
        else:
            #print("payload: ")
            #print(self.incomingState["payload"])
            if input["type"]!= "object" and self.incomingState["payload"]["type"] != "object":
                if "source" in input:
                    i_source = input["source"]
                    p_source = self.incomingState["payload"]["source"]
                    if i_source["type"] == p_source["type"]:# does this need a closing else?
                        if i_source["type"] == "event":
                            return True
                        if "name" in i_source:
                            if i_source["name"] == p_source["name"]:
                                if "pos" in i_source:
                                    if i_source["pos"] == "last":#finish this
                                        for i in reversed(self.previousInteractions):
                                            name = None
                                            if i.node["type"] == "system-action-node":
                                                name = i.node["thingAction"]
                                            if  i.node["type"] == "system-property-node":
                                                name = i.node["thingProperty"]
                                            if name == input["name"]:
                                                if p_source["id"] == i.node["id"]:
                                                    return True
                                                else:
                                                    return False
                                else:
                                    return True
                            else:
                                return True
                        else:
                            return True
                else:
                    return True
            elif input["type"] == "object" and self.incomingState["payload"]["type"] == "object":
                for k,v in input["properties"].items():
                    if k not in self.incomingState["payload"]["properties"]:
                        return False
                    if "source" in v:
                        i_source = v["source"]
                        p_source = self.incomingState["payload"]["properties"][k]["source"]
                        if i_source["type"] == p_source["type"]:
                            if i_source["type"] == "event":
                                return True
                            if "name" in i_source:
                                if i_source["name"] == p_source["name"]:
                                    if "pos" in i_source:
                                        if i_source["pos"] == "last":#finish this
                                            for i in reversed(self.previousInteractions):
                                                name = None
                                                if i.node["type"] == "system-action-node":
                                                    name = i.node["thingAction"]
                                                if  i.node["type"] == "system-property-node":
                                                    name = i.node["thingProperty"]
                                                if name == input["name"]:        
                                                    return True
                                                else:
                                                    return False
                                    else:
                                        return True
                                else:
                                    return True
                            else:
                                return True
                    else:
                        return True
            return False


    def preConditionsMatch(self, pre_nodes):
        if pre_nodes == []:
            return True
        else:
            prev=[]
            for i in self.previousInteractions:
                #print(i.node["type"])
                if i.node["type"] == "system-action-node":
                    if i.node["thingAction"] in pre_nodes:
                        prev.append(i.node["thingAction"])
                if i.node["type"] == "system-property-node":
                    if i.node["mode"] == "write":
                        if i.node["thingProperty"] in pre_nodes:
                            prev.append(i.node["thingProperty"])
            if pre_nodes == prev:
                return True
            else:
                return False

    def match(self, subflow_matches):
        #print("subflow matches: ")
        #print(subflow_matches)
        candidates = []
        for i in subflow_matches:
            if i[0] == self.node["thingProperty"]:
                candidates.append(i)
        #print("candidates: ")
        #print(candidates)
        match ={"preConditionMatch": False, "conditionsMatch": False, "inputMatch": False}
        candidates = [x for x in candidates if self.preConditionsMatch(x[1]["pre_nodes"])]
        if candidates != []:
            match["preConditionMatch"] = True
            candidates = [x for x in candidates if self.conditionsMatch(x[1]["conditions"])]
            if candidates != []:
                match["conditionsMatch"] = True
                candidates = [x for x in candidates if self.inputMatch(x[1]["input"])]
                if candidates != []:
                    match["inputMatch"] = True

        for i in candidates:#should be no more than one candidate but just in case checks list, this check prevents multiple nodes matching against the same case.
            subflow_matches.remove(i)
        #print("status: " + str(status))
        status = match["preConditionMatch"] and match["conditionsMatch"] and match["inputMatch"]
        return {"status": status, "match": match, "candidates": candidates}
