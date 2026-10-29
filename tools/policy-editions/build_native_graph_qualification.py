"""Emit a manual, built-in-only fictional graph evaluator; never a writer.

Native source/receipt authenticity and pre-write integration remain separate.
No flow, connection or service operation occurs while building this definition.
"""
from copy import deepcopy


def build_definition():
    def action(kind, inputs, previous=None):
        return {'type': kind, 'inputs': inputs, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def compose(value, previous=None):
        return action('Compose', value, previous)
    def select(source, value, previous):
        return action('Select', {'from': source, 'select': value}, previous)
    def query(source, where, previous):
        return action('Query', {'from': source, 'where': where}, previous)
    def pin(expr):
        return 'string(createArray(' + ','.join(expr+"?['"+k+"']" for k in
            ('DocumentUID','policyEdition','resourceReference','nativeVersionRef','sha256')) + '))'
    def identity(expr):
        return 'string(createArray('+expr+"?['DocumentUID'],"+expr+"?['policyEdition']))"
    def present(expr):
        return 'not(empty(trim(string('+expr+'))))'
    def hex64(expr):
        stripped='toLower(string('+expr+'))'
        for char in '0123456789abcdef':
            stripped="replace("+stripped+",'"+char+"','')"
        return 'and(equals(length(string('+expr+')),64),equals('+stripped+",''))"
    string={'type':'string'}
    pin_schema={'type':'object','properties':{k:deepcopy(string) for k in
        ('DocumentUID','policyEdition','resourceReference','nativeVersionRef','sha256')},
        'required':['DocumentUID','policyEdition','resourceReference','nativeVersionRef','sha256']}
    node_schema=deepcopy(pin_schema)
    node_schema['properties'].update({'FictionalTest':{'type':'boolean'},'downloadedSHA256':string,
        'representationKind':string,'issuedReceiptReference':string})
    node_schema['required']+=['FictionalTest','downloadedSHA256','representationKind','issuedReceiptReference']
    edge_schema={'type':'object','properties':{'replacement':pin_schema,'replaced':pin_schema,
        'FictionalTest':{'type':'boolean'},'evidenceReference':string},
        'required':['replacement','replaced','FictionalTest','evidenceReference']}
    schema={'type':'object','properties':{'mode':string,'nodes':{'type':'array','items':node_schema},
        'relationships':{'type':'array','items':edge_schema},'proposed':edge_schema,
        'snapshot':{'type':'object','properties':{'complete':{'type':'boolean'},'hasNextLink':{'type':'boolean'},
            'beforeToken':string,'afterToken':string,'evidenceReference':string},
            'required':['complete','hasNextLink','beforeToken','afterToken','evidenceReference']}},
        'required':['mode','nodes','relationships','proposed','snapshot']}
    a={}
    a['Validate_input']={'type':'If','expression':"@and(not(empty(triggerBody()?['text'])),lessOrEquals(length(string(triggerBody()?['text'])),150000))",
        'actions':{'Input_bounded':compose(True)},'else':{'actions':{'Refuse_input':action('Terminate',{'runStatus':'Failed','runError':{'code':'FIXTURE_INPUT','message':'Bounded fictional JSON input required; no effects.'}})}},'runAfter':{}}
    a['Parse_graph']=action('ParseJson',{'content':"@json(triggerBody()?['text'])",'schema':schema},'Validate_input')
    n="item()"
    valid=['equals(item()?[\'FictionalTest\'],true)',hex64("item()?['sha256']"),"equals(item()?['downloadedSHA256'],item()?['sha256'])"]
    valid += [present("item()?['"+k+"']") for k in ('DocumentUID','policyEdition','resourceReference','nativeVersionRef')]
    valid += ["not(equals(trim(item()?['nativeVersionRef']),'*'))"]
    a['Node_records']=select("@body('Parse_graph')?['nodes']",{'key':'@'+pin(n),'identity':'@'+identity(n),
        'valid':'@and('+','.join(valid)+')','issued':"@and(equals(item()?['representationKind'],'issued'),not(empty(trim(item()?['issuedReceiptReference']))))"},'Parse_graph')
    a['Node_keys']=select("@body('Node_records')","@item()?['key']",'Node_records')
    a['Identity_keys']=select("@body('Node_records')","@item()?['identity']",'Node_keys')
    a['Bad_nodes']=query("@body('Node_records')","@not(equals(item()?['valid'],true))",'Identity_keys')
    a['Unissued_nodes']=query("@body('Node_records')","@not(equals(item()?['issued'],true))",'Bad_nodes')
    a['Unissued_keys']=select("@body('Unissued_nodes')","@item()?['key']",'Unissued_nodes')
    a['All_edge_inputs']=compose("@union(body('Parse_graph')?['relationships'],createArray(body('Parse_graph')?['proposed']))",'Unissued_keys')
    a['Edges']=select("@outputs('All_edge_inputs')",{'from':'@'+pin("item()?['replacement']"),'to':'@'+pin("item()?['replaced']"),
        'fromIdentity':'@'+identity("item()?['replacement']"),'toIdentity':'@'+identity("item()?['replaced']"),
        'valid':"@and(equals(item()?['FictionalTest'],true),not(empty(trim(item()?['evidenceReference']))))"},'All_edge_inputs')
    a['Pair_keys']=select("@body('Edges')","@string(createArray(item()?['from'],item()?['to']))",'Edges')
    a['Bad_edges']=query("@body('Edges')","@not(equals(item()?['valid'],true))",'Pair_keys')
    a['Self_edges']=query("@body('Edges')","@equals(item()?['fromIdentity'],item()?['toIdentity'])",'Bad_edges')
    a['Unknown_edges']=query("@body('Edges')","@or(not(contains(body('Node_keys'),item()?['from'])),not(contains(body('Node_keys'),item()?['to'])))",'Self_edges')
    a['Archive_edges']=query("@body('Edges')","@or(contains(body('Unissued_keys'),item()?['from']),contains(body('Unissued_keys'),item()?['to']))",'Unknown_edges')
    snap="body('Parse_graph')?['snapshot']"
    checks=[('native-generalisation-unqualified',"equals(body('Parse_graph')?['mode'],'fictional-qualification')"),
        ('graph:capacity-limit',"and(greater(length(body('Node_keys')),0),lessOrEquals(length(body('Node_keys')),64),lessOrEquals(length(body('Parse_graph')?['relationships']),256))"),
        ('graph:incomplete-or-changed',"and(equals("+snap+"?['complete'],true),equals("+snap+"?['hasNextLink'],false),"+present(snap+"?['evidenceReference']")+','+present(snap+"?['beforeToken']")+",not(equals(trim("+snap+"?['beforeToken']),'*')),equals("+snap+"?['beforeToken'],"+snap+"?['afterToken']))"),
        ('graph:ambiguous-identity',"equals(length(body('Identity_keys')),length(union(body('Identity_keys'),body('Identity_keys'))))"),
        ('graph:duplicate-edge',"and(equals(length(outputs('All_edge_inputs')),add(length(body('Parse_graph')?['relationships']),1)),equals(length(body('Pair_keys')),length(union(body('Pair_keys'),body('Pair_keys')))))")]
    for name,code in [('Bad_nodes','graph:unverified-node'),('Bad_edges','graph:incomplete-edge'),('Self_edges','graph:self-link'),('Unknown_edges','graph:unknown-target'),('Archive_edges','graph:archive-only-or-unissued')]:
        checks.append((code,"empty(body('"+name+"'))"))
    reasons='@createArray('+','.join("if("+expr+",'','"+code+"')" for code,expr in checks)+')'
    a['Refusal_reasons']=query(reasons,"@not(empty(item()))",'Archive_edges')
    a['Initialize_nodes']=action('InitializeVariable',{'variables':[{'name':'remaining_nodes','type':'Array','value':"@body('Node_keys')"}]},'Refusal_reasons')
    a['Initialize_edges']=action('InitializeVariable',{'variables':[{'name':'remaining_edges','type':'Array','value':"@body('Edges')"}]},'Initialize_nodes')
    a['Initialize_stalled']=action('InitializeVariable',{'variables':[{'name':'stalled','type':'Boolean','value':False}]},'Initialize_edges')
    loop={
        'Cycle_targets':select("@variables('remaining_edges')","@item()?['to']",None),
        'Cycle_zero_nodes':query("@variables('remaining_nodes')","@not(contains(body('Cycle_targets'),item()))",'Cycle_targets'),
        'Cycle_keep_nodes':query("@variables('remaining_nodes')","@not(contains(body('Cycle_zero_nodes'),item()))",'Cycle_zero_nodes'),
        'Cycle_keep_edges':query("@variables('remaining_edges')","@not(contains(body('Cycle_zero_nodes'),item()?['from']))",'Cycle_keep_nodes'),
        'Set_nodes':action('SetVariable',{'name':'remaining_nodes','value':"@body('Cycle_keep_nodes')"},'Cycle_keep_edges'),
        'Set_edges':action('SetVariable',{'name':'remaining_edges','value':"@body('Cycle_keep_edges')"},'Set_nodes'),
        'Set_stalled':action('SetVariable',{'name':'stalled','value':"@empty(body('Cycle_zero_nodes'))"},'Set_edges')}
    base={'qualificationScope':'native-fictional-graph-engine-only','nativeWriterEnabled':False,'controlledPublicationQualified':False,
        'nativeSnapshotAuthenticityQualified':False,'sourceAcquisitionQualified':False,'issuedReceiptAuthenticityQualified':False,
        'actorAuthorityQualified':False,'writesPerformed':0}
    cycle={'type':'Until','expression':"@or(empty(variables('remaining_nodes')),equals(variables('stalled'),true))",'limit':{'count':64,'timeout':'PT5M'},'actions':loop,'runAfter':{}}
    a['Evaluate_graph']={'type':'If','expression':"@empty(body('Refusal_reasons'))",'actions':{
        'Remove_acyclic_nodes':cycle,'Native_graph_result':compose({**base,'consistent':"@empty(variables('remaining_nodes'))",'reasons':"@if(empty(variables('remaining_nodes')),json('[]'),createArray('graph:cycle'))"},'Remove_acyclic_nodes')},
        'else':{'actions':{'Native_graph_hold':compose({**base,'consistent':False,'reasons':"@body('Refusal_reasons')"})}},'runAfter':{'Initialize_stalled':['Succeeded']}}
    return {'$schema':'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#',
        'contentVersion':'1.0.0.0','parameters':{'$authentication':{'type':'SecureObject','defaultValue':{}},'$connections':{'type':'Object','defaultValue':{}}},
        'triggers':{'manual':{'type':'Request','kind':'Button','inputs':{'schema':{'type':'object','properties':{'text':{'type':'string','title':'Fictional graph JSON','x-ms-dynamically-added':True,'x-ms-content-hint':'TEXT'}},'required':['text']}},'runtimeConfiguration':{'concurrency':{'runs':1}}}},'actions':a}
