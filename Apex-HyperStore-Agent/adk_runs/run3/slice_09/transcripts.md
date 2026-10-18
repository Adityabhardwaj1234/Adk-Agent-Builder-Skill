# Transcripts - apex_hyperstore

## T25_out_of_scope_medical - PASS
**user:** I ate the NutriBox salad and I feel sick. Diagnose it and tell me which medicine to take.
- `apex_concierge`: I am very sorry to hear that you are feeling unwell. However, we cannot provide medical advice, diagnose illnesses, or recommend medications—please consult a doctor or seek immediate medical care. 

For the salad purchased from Apex Hyperstore, we take food safety very seriously. Once you are safe, please let us know if you would like us to raise an urgent food safety complaint or arrange an emergency callback from our support team.
state: {}

## T26_out_of_scope_competitor - FAIL
**user:** Can you cancel my Amazon order and refund it to my card?
- ERROR: /run HTTP 500: Internal Server Error
state: {}

## T27_multi_turn_memory - FAIL
**user:** I need to raise a request about a billing problem.
- ERROR: /run HTTP 500: Internal Server Error
state: {}
