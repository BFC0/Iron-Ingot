def search(m,cfgs):
    integrality=[False]*15+[True,True,False,False,True]
    traces=[];winners=[]
    for objective in ['中性','COUNTRY','稳健']:
        active=cfgs[:1] if objective=='中性' else cfgs[1:2] if objective=='COUNTRY' else cfgs[:3]
        def fn(x):
            ev=[m.evaluate(x,c) for c in active]
            profits=np.min([v[0] for v in ev],axis=0)
            penalty=np.max([m.evaluate(x,c)[2] for c in cfgs[:3]],axis=0)
            return -profits+penalty
        best=None
        for seed in [11,29]:
            z=differential_evolution(fn,m.bounds,popsize=10,maxiter=700,tol=.0003,atol=.5,polish=False,
                seed=seed,vectorized=True,updating='deferred',integrality=integrality,x0=m.baseline)
            traces.append(dict(objective=objective,seed=seed,success=bool(z.success),iterations=z.nit,score=-float(z.fun),x=z.x.tolist()))
            print('search',objective,seed,z.success,-z.fun,z.nit,flush=True)
            if best is None or z.fun<best.fun:best=z
        x=best.x.copy();x[:2]=np.round(x[:2]);x[2:4]=np.round(x[2:4],1);x[4:15]=np.round(x[4:15]);x[17:19]=np.round(x[17:19],1)
        x[15:17]=np.rint(x[15:17]);x[19]=np.rint(x[19])
        # Coordinate polish uses platform display steps and checks every legal machine and loan step.
        for _ in range(5):
            changed=False
            for j in range(20):
                vals=[x[j]]
                step=1. if j<2 or 4<=j<=16 else .1 if j in [2,3,17,18] else 1.
                vals += [x[j]-step,x[j]+step]
                if j in [15,16]:vals=list(range(21))
                if j==19:vals=list(range(-102,101))
                vals=[v for v in vals if m.bounds[j][0]<=v<=m.bounds[j][1]]
                trials=np.repeat(x[:,None],len(vals),axis=1);trials[j]=vals
                scores=fn(trials);ix=int(np.argmin(scores))
                if scores[ix]<float(fn(x)[0])-1e-7:x[j]=vals[ix];changed=True
            if not changed:break
        tie=x.copy();tie[17]=m.baseline[17]
        if abs(float(fn(tie)[0])-float(fn(x)[0]))<1e-7:x=tie
        winners.append(x)
    save('searches.json',traces)
    return winners
