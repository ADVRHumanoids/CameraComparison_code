"""Numerical methods used by the standalone paper analysis.

Called by: scripts.analyze and scripts.analysis_tables; no CLI or filesystem I/O.
Inputs/outputs: float64 arrays; metres for depth moments, mm for image profiles,
               degrees for angles, marker-cell units for printed-boundary distance.
Methods adapted from the existing summarize, plane, profile and boundary scripts.
Moving-block intervals describe within-recording variation, not setup repeatability.
"""
import warnings
import cv2
import numpy as np

METRICS = ['bias_m', 'absolute_bias_m', 'spatial_sd_m', 'rmse_m', 'valid_fraction', 'temporal_mean_sd_m']
BINS = np.array([0, .1, .2, .3, .4, .5, .75, 1, 2.5])

def acf(x, maxlag=None):
    x=np.asarray(x,float); x=x-x.mean()
    maxlag=min(len(x)//3,100) if maxlag is None else maxlag
    denominator=x@x
    return np.ones(maxlag+1) if denominator < 1e-24 else np.array([x[:len(x)-k]@x[k:]/denominator for k in range(maxlag+1)])

def block_length(x):
    correlations=acf(x)
    for k in range(1,len(correlations)-4):
        if np.all(np.abs(correlations[k:k+5]) < 0.1):
            return k, False
    return max(1,len(x)//4), True

def estimates(x):
    """Column layout is bias, spatial variance, squared RMSE, coverage."""
    mean=x.mean(axis=-2)
    return np.stack((mean[...,0],np.abs(mean[...,0]),np.sqrt(np.maximum(0,mean[...,1])),
                     np.sqrt(mean[...,2]),mean[...,3],np.std(x[...,0],axis=-1)),axis=-1)

def bootstrap(x,length,rng,reps=2000):
    n=len(x); blocks=int(np.ceil(n/length))
    # Moving blocks never wrap from the end of a recording back to its beginning.
    starts=rng.integers(0,n-length+1,size=(reps,blocks))
    indices=(starts[...,None]+np.arange(length)).reshape(reps,-1)[:,:n]
    return estimates(x[indices])

def recording_summary(frame, seed):
    x=np.column_stack((frame.bias_m,frame.spatial_var_m2,frame.rmse_m**2,frame.valid_fraction))
    length,persistent=block_length(x[:,0])
    # Cover dependence of spatial error/coverage too, not only dependence of the mean.
    for column in range(1,4):
        if np.std(x[:,column])>1e-12:
            other,flag=block_length(x[:,column]);length=max(length,other);persistent |= flag
    length=min(length,max(1,len(x)//4))
    rng=np.random.default_rng(seed)
    samples=bootstrap(x,length,rng)
    point=estimates(x)
    sensitivity_samples={label:bootstrap(x,min(len(x),max(1,int(length*factor))),np.random.default_rng(seed+int(factor*100)))
                         for factor,label in [(0.5,'half'),(2,'double')]}
    timestamps=frame.timestamp_ns.to_numpy(np.int64)
    intervals=np.diff(timestamps)/1e9
    bias_sd=np.std(x[:,0]);chunk=max(1,len(x)//3)
    drift=float((x[-chunk:,0].mean()-x[:chunk,0].mean())/bias_sd) if bias_sd>0 else 0
    result=dict(frames=len(frame),block_frames=length,persistent_correlation=persistent,
                drift_in_sd=drift,interval_reliable=not persistent and abs(drift)<1,
                median_interval_s=float(np.median(intervals)),max_interval_s=float(np.max(intervals)),
                duration_s=(timestamps[-1]-timestamps[0])/1e9,
                lag1_acf=float(acf(x[:,0])[1]),effective_n_diagnostic=float(len(x)/(1+2*np.maximum(acf(x[:,0])[1:],0).sum())))
    for j,name in enumerate(METRICS):
        result[name]=float(point[j])
        result[name+'_lo'],result[name+'_hi']=np.quantile(samples[:,j],[0.025,0.975])
        for label,sensitivity in sensitivity_samples.items():
            result[name+'_'+label+'_lo'],result[name+'_'+label+'_hi']=np.quantile(sensitivity[:,j],[0.025,0.975])
    result['negative_fraction']=float(frame.negative_fraction.mean())
    result['positive_fraction']=float(frame.positive_fraction.mean())
    result['positive_contribution_m']=float(frame.positive_contribution_m.mean())
    result['negative_contribution_m']=float(frame.negative_contribution_m.mean())
    result['plane_residual_sd_m']=float(np.sqrt(np.mean(frame.plane_residual_sd_m**2)))
    return result,samples

def fit_plane(x,y,z):
    """Match the original depth-axis least-squares plane using centered moments."""
    x,y,z=[np.asarray(v,dtype=np.float64) for v in [x,y,z]]
    means=np.array([x.mean(),y.mean(),z.mean()])
    dx,dy,dz=x-means[0],y-means[1],z-means[2]
    gram=np.array([[dx@dx,dx@dy],[dx@dy,dy@dy]])
    assert np.linalg.cond(gram)<1e12,'Degenerate ROI plane fit'
    a,b=np.linalg.solve(gram,np.array([dx@dz,dy@dz]))
    predicted=a*dx+b*dy
    residual=dz-predicted
    spatial_var=float(dz@dz/len(z));residual_var=float(residual@residual/len(z))
    fitted_var=float(predicted@predicted/len(z))
    np.testing.assert_allclose(spatial_var,fitted_var+residual_var,atol=1e-13,rtol=1e-10)
    return dict(a=a,b=b,c=means[2]-a*means[0]-b*means[1],
                tilt_deg=np.degrees(np.arctan(np.hypot(a,b))),
                x_slope_deg=np.degrees(np.arctan(a)),y_slope_deg=np.degrees(np.arctan(b)),
                spatial_var_m2=spatial_var,residual_var_m2=residual_var,fitted_var_m2=fitted_var)

def frame_geometry(a, b):
    """Signed directional slopes and unit normals consistently oriented toward +Z."""
    slopes = np.column_stack([a, b])
    angles = np.degrees(np.arctan(slopes))
    normals = np.column_stack([-slopes, np.ones(len(slopes))])
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    return angles, normals

def normal_angle(left, right):
    """Angular separation of equally oriented unit normals, stable at zero angle."""
    return float(np.degrees(np.arctan2(np.linalg.norm(np.cross(left, right)), left @ right)))

def coordinates(pixel):
    """Keep one recording-wide native-coordinate scale, including missing rows."""
    pixel = np.asarray(pixel, dtype=float)
    if len(pixel) < 3 or np.ptp(pixel) == 0:
        raise ValueError('At least three distinct pixel positions are required')
    return 2 * (pixel - pixel.min()) / np.ptp(pixel) - 1

def fit_profile(position, error):
    """Quadratic fit in fixed image coordinates, giving directly readable contrasts.

    f(x)=a+b*x+c*x^2, x in [-1,1]. Gradient=2b is end-to-end change;
    bow=c is [f(-1)+f(1)]/2-f(0), positive when edges are farther away.
    All input errors and returned contrasts are in millimetres.
    """
    valid = np.isfinite(error)
    x, y = position[valid], error[valid]
    if len(y) < 3:
        raise ValueError('Profile has fewer than three finite positions')
    design = np.column_stack([np.ones(len(x)), x, x*x])
    coef, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    if rank != 3:
        raise ValueError('Profile polynomial is rank deficient')
    return dict(offset_mm=float(y.mean()), midpoint_error_mm=float(coef[0]),
                gradient_mm=float(2*coef[1]), bow_mm=float(coef[2]),
                irregular_rms_mm=float(np.sqrt(np.mean((y-design@coef)**2))),
                occupied_positions=len(y))

def profiles(error):
    """Median across columns for each row, and across rows for each column."""
    # Empty polygon corners intentionally stay NaN and are reported as absent.
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='All-NaN slice encountered', category=RuntimeWarning)
        return [np.nanmedian(error, axis=1), np.nanmedian(error, axis=0)]

def marker_grid(marker_id):
    image=cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250),marker_id,60)
    return image[5::10,5::10]>127

def transitions(grid):
    """Only colour-changing cell interfaces; omit the outer silhouette."""
    segments=[]
    for row in range(6):
        for col in range(1,6):
            if grid[row,col-1]!=grid[row,col]:segments.append(((col,row),(col,row+1)))
    for row in range(1,6):
        for col in range(6):
            if grid[row-1,col]!=grid[row,col]:segments.append(((col,row),(col+1,row)))
    return np.asarray(segments,dtype=float)

def edge_distance(points,segments):
    distance=np.full(len(points),np.inf)
    for a,b in segments:
        v=b-a;t=np.clip((points-a)@v/(v@v),0,1)
        distance=np.minimum(distance,np.linalg.norm(points-a-t[:,None]*v,axis=1))
    return distance

def summarize_band(sd,distance,keep,white,coverage,width):
    edge=keep&(distance<=width);center=keep&(distance>=.30)
    result=dict(edge_pixels=int(edge.sum()),interior_pixels=int(center.sum()))
    for label,mask in [('edge',edge),('interior',center)]:
        result[label+'_median_sd_mm']=float(np.median(sd[mask])) if mask.any() else np.nan
        result[label+'_rms_sd_mm']=float(np.sqrt(np.mean(sd[mask]**2))) if mask.any() else np.nan
        result[label+'_mean_coverage']=float(coverage[mask].mean()) if mask.any() else np.nan
    denominator=result['interior_median_sd_mm']
    result['edge_interior_ratio']=result['edge_median_sd_mm']/denominator if denominator>1e-9 else np.nan
    result['absolute_drop_mm']=denominator-result['edge_median_sd_mm']
    for label,colour in [('white',white),('black',~white)]:
        a=edge&colour;b=center&colour
        result[label+'_edge_pixels']=int(a.sum());result[label+'_interior_pixels']=int(b.sum())
        den=np.median(sd[b]) if b.any() else np.nan
        result[label+'_ratio']=float(np.median(sd[a])/den) if a.sum()>=10 and b.sum()>=10 and den>1e-9 else np.nan
    return result

