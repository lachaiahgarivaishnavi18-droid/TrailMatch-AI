export type Patient = {id:string;code:string;age:number|null;sex:string;conditions:string[];medications:string[];allergies:string[];labs:Record<string,{value:number;unit:string}>;notes:string;history_complete:boolean;synthetic:boolean};
export type Trial = {id:string;title:string;conditions:string[];interventions:string[];sponsor:string;phase:string;status:string;locations:string[];summary:string;eligibility:string;min_age:number|null;max_age:number|null;sex:string;source:string;source_url?:string;retrieved_at?:string;synthetic:boolean};
export type Criterion = {kind:string;attribute:string;operator:string;value:number|string|null;unit:string|null;original:string;explicit:boolean;review_required:boolean};
export type Evidence = {criterion:Criterion;status:string;patient_value:string;explanation:string};
export type Result = {trial:Trial;similarity:number;score:number;disposition:string;evidence:Evidence[];summary:string};
export type Run = {id:string;patient_id:string;created_at:string;profile:{patient:Patient;normalized_conditions:string[];entities:{type:string;text:string;confirmed:boolean}[];missing_information:string[];provenance:unknown[]};results:Result[];logs:{agent:string;duration_ms:number;started_at:string;summary:string}[];retrieval_provider:string;disclaimer:string};
export type RunSummary = {id:string;patient_id:string;patient_code:string;created_at:string;result_count:number};
export type Analytics = {patients:number;trials:number;runs:number;recruiting:number;synthetic_trials:number;dispositions:Record<string,number>};
