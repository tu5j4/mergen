"""Context encoder / current-only decoder attention, shared by training and serving."""
def encode(tokenizer,row,with_target=True):
    prefix='[history]\n'+'\n'.join(row['previous_sources'][-3:])+'\n[current]\n'
    kwargs=dict(return_offsets_mapping=True)
    if with_target:kwargs['text_target']=row['target']
    feature=tokenizer(prefix+row['source'],**kwargs)
    offsets=feature.pop('offset_mapping')
    mask=[int(end>len(prefix) or token==tokenizer.eos_token_id) for (start,end),token in zip(offsets,feature['input_ids'])]
    assert any(mask) and len(mask)==len(feature['input_ids'])
    return dict(feature),mask

def generate(model,tokenizer,row,device='cuda',return_details=False,preserve_stutter=True):
    import torch
    feature,mask=encode(tokenizer,row,False)
    while len(feature['input_ids'])>384 and row['previous_sources']:
        row=dict(row,previous_sources=row['previous_sources'][1:]);feature,mask=encode(tokenizer,row,False)
    if len(feature['input_ids'])>384:raise ValueError('tek replik 384 token sınırını aşıyor')
    batch={k:torch.tensor([v],device=device) for k,v in feature.items()}
    cross=torch.tensor([mask],device=device)
    encoder=model.get_encoder()(input_ids=batch['input_ids'],attention_mask=batch['attention_mask'],return_dict=True)
    output=model.generate(encoder_outputs=encoder,attention_mask=cross,
        forced_bos_token_id=tokenizer.convert_tokens_to_ids('tur_Latn'),num_beams=4,max_new_tokens=192,
        repetition_penalty=1.,no_repeat_ngram_size=0)
    raw=tokenizer.decode(output[0],skip_special_tokens=True).strip()
    from .nllb_stutter import preserve_initial_stutter
    text=preserve_initial_stutter(row['source'],raw) if preserve_stutter else raw
    if return_details:
        return dict(translation=text,raw_translation=raw,initial_stutter_restored=text!=raw,output_tokens=len(output[0]),
            limit_reached=len(output[0])>=193 and int(output[0][-1])!=tokenizer.eos_token_id,
            source_tokens=len(feature['input_ids']),cross_attention_tokens=sum(mask),history_used=row['previous_sources'][-3:])
    return text


def generate_batch(model,tokenizer,rows,device='cuda'):
    """Batch independent source histories, keeping current-only masks separate."""
    import torch
    if not rows:return []
    features=[];masks=[]
    for row in rows:
        feature,mask=encode(tokenizer,row,False)
        while len(feature['input_ids'])>384 and row['previous_sources']:
            row=dict(row,previous_sources=row['previous_sources'][1:])
            feature,mask=encode(tokenizer,row,False)
        if len(feature['input_ids'])>384:raise ValueError('tek replik 384 token sınırını aşıyor')
        features.append(feature);masks.append(mask)
    inputs=tokenizer.pad(features,padding=True,return_tensors='pt').to(device)
    width=inputs['input_ids'].shape[1]
    left=tokenizer.padding_side=='left'
    cross=torch.tensor([([0]*(width-len(m))+m if left else m+[0]*(width-len(m))) for m in masks],device=device)
    encoder=model.get_encoder()(**inputs,return_dict=True)
    outputs=model.generate(encoder_outputs=encoder,attention_mask=cross,
        forced_bos_token_id=tokenizer.convert_tokens_to_ids('tur_Latn'),num_beams=4,max_new_tokens=192,
        repetition_penalty=1.,no_repeat_ngram_size=0)
    from .nllb_stutter import preserve_initial_stutter
    results=[]
    for row,output in zip(rows,outputs.tolist()):
        # Finished rows are padded while longer rows continue. Ignore only the
        # padding after a real EOS, not the decoder's initial EOS/start token.
        try:output=output[:output.index(tokenizer.eos_token_id,1)+1]
        except ValueError:pass
        raw=tokenizer.decode(output,skip_special_tokens=True).strip()
        results.append(dict(translation=preserve_initial_stutter(row['source'],raw),
            limit_reached=len(output)>=193 and output[-1]!=tokenizer.eos_token_id))
    return results
