"""
Copyright (c) 2006-2011, NIPY Developers
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

    * Redistributions of source code must retain the above copyright
       notice, this list of conditions and the following disclaimer.

    * Redistributions in binary form must reproduce the above
       copyright notice, this list of conditions and the following
       disclaimer in the documentation and/or other materials provided
       with the distribution.

    * Neither the name of the NIPY Developers nor the names of any
       contributors may be used to endorse or promote products derived
       from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


Nitime 0.6 code slightly adapted by D. Mingers, Aug 2016
d.mingers@web.de

CONTENT OF THIS FILE:

Spectral transforms are used in order to estimate the frequency-domain
representation of time-series. Several methods can be used and this module
contains implementations of several algorithms for the calculation of spectral
transforms.

"""

import numpy as np
# import matplotlib.mlab as mlab
import scipy.linalg as linalg
import scipy.signal as sig
import scipy.interpolate as interpolate
import scipy.fftpack as fftpack
import spectral as spectral
import warnings

import multitaper_utils as utils

# Set global variables for the default NFFT to be used in spectral analysis and
# the overlap:
default_nfft = 64
default_n_overlap = int(np.ceil(default_nfft // 2))


def get_spectra(time_series, method=None):
    r"""
    Compute the spectra of an n-tuple of time series and all of
    the pairwise cross-spectra.

    Parameters
    ----------
    time_series : float array
        The time-series, where time is the last dimension

    method : dict, optional

        contains: this_method:'welch'
           indicates that :func:`mlab.psd` will be used in
           order to calculate the psd/csd, in which case, additional optional
           inputs (and default values) are:

               NFFT=64

               Fs=2pi

               detrend=mlab.detrend_none

               window=mlab.window_hanning

               n_overlap=0

        this_method:'multi_taper_csd'
           indicates that :func:`multi_taper_psd` used in order to calculate
           psd/csd, in which case additional optional inputs (and default
           values) are:

               BW=0.01

               Fs=2pi

               sides = 'onesided'

    Returns
    -------

    f : float array
        The central frequencies for the frequency bands for which the spectra
        are estimated

    fxy : float array
        A semi-filled matrix with the cross-spectra of the signals. The csd of
        signal i and signal j is in f[j][i], but not in f[i][j] (which will be
        filled with zeros). For i=j fxy[i][j] is the psd of signal i.

    """
    if method is None:
        method = {'this_method': 'multi_taper_csd'}  # The default
    # If no choice of method was explicitly set, but other parameters were
    # passed, assume that the method is multitapering:
    this_method = method.get('this_method', 'multi_taper_csd')

    if this_method == 'welch':
        NFFT = method.get('NFFT', default_nfft)
        Fs = method.get('Fs', 2 * np.pi)
        detrend = method.get('detrend', 'constant') #mlab.detrend_none)
        window = method.get('window', 'hanning') #mlab.window_hanning)
        noverlap = method.get('noverlap', int(np.ceil(NFFT / 2)))
        scaling = method.get('scaling', 'spectrum')

        # The length of the spectrum depends on how many sides are taken, which
        # depends on whether or not this is a complex object:
        if np.iscomplexobj(time_series):
            fxy_len = NFFT
        else:
            fxy_len = NFFT // 2 + 1

        # If there is only 1 channel in the time-series:
        if len(time_series.shape) == 1 or time_series.shape[0] == 1:
            temp, f = spectral._welch( # mlab.csd(
                time_series, time_series,
                fs=Fs, window=window, noverlap=noverlap,
                nfft=NFFT, detrend=detrend) # scale_by_freq=True)

            fxy = temp.squeeze()  # the output of mlab.csd has a weird shape
        else:
            fxy = np.zeros((time_series.shape[0],
                            time_series.shape[0],
                            fxy_len), dtype=complex)  # Make sure it's complex

            for i in range(time_series.shape[0]):
                for j in range(i, time_series.shape[0]):
                    #Notice funny indexing, in order to conform to the
                    #convconventions of the other methods:
                    temp, f = spectral._welch(time_series[j], time_series[i],
                                              fs=Fs, window=window,
                                              noverlap=noverlap,
                                              nfft=NFFT, detrend=detrend)
                                       # scale_by_freq=True)

                    fxy[i][j] = temp.squeeze()  # the output of mlab.csd has a
                                                # weird shape
    if this_method == 'multi_taper_csd':
        mdict = method.copy()
        func = eval(mdict.pop('this_method'))
        freqs, fxy = func(time_series, **mdict)
        f = utils._circle_to_hz(freqs, mdict.get('Fs', 2 * np.pi))

    else:
        raise ValueError("Unknown method provided")

    return f, fxy.squeeze()


def get_spectra_bi(x, y, method=None):
    r"""
    Computes the spectra of two timeseries and the cross-spectrum between them

    Parameters
    ----------

    x,y : float arrays
        Time-series data

    method : dict, optional
       See :func:`get_spectra` documentation for details

    Returns
    -------
    f : float array
        The central frequencies for the frequency
        bands for which the spectra are estimated
    fxx : float array
         The psd of the first signal
    fyy : float array
        The psd of the second signal
    fxy : float array
        The cross-spectral density of the two signals

    """
    f, fij = get_spectra(np.vstack((x, y)), method=method)
    fxx = fij[ 0, 0 ].real
    fyy = fij[ 1, 1 ].real
    fxy = fij[ 0, 1 ]
    return f, fxx, fyy, fxy


# The following spectrum estimates are normalized to the convention
# adopted by MATLAB (or at least spectrum.psd)
# By definition, Sxx(f) = DTFT{Rxx(n)}, where Rxx(n) is the autocovariance
# function of x(n). Therefore the integral from
# [-Fs/2, Fs/2] of Sxx(f)*df is Rxx(0).
# And from the definition of Rxx(n),
# Rxx(0) = Expected-Value{x(n)x*(n)} = Expected-Value{ |x|^2 },
# which is estimated as (x*x.conj()).mean()
# In other words, sum(Sxx) * Fs / NFFT ~ var(x)


def dpss_windows(N, NW, Kmax, interp_from=None, interp_kind='linear'):
    """
    Returns the Discrete Prolate Spheroidal Sequences of orders [0,Kmax-1]
    for a given frequency-spacing multiple NW and sequence length N.

    Parameters
    ----------
    N : int
        sequence length
    NW : float, unitless
        standardized half bandwidth corresponding to 2NW = BW/f0 = BW*N*dt
        but with dt taken as 1
    Kmax : int
        number of DPSS windows to return is Kmax (orders 0 through Kmax-1)
    interp_from : int (optional)
        The dpss can be calculated using interpolation from a set of dpss
        with the same NW and Kmax, but shorter N. This is the length of this
        shorter set of dpss windows.
    interp_kind : str (optional)
        This input variable is passed to scipy.interpolate.interp1d and
        specifies the kind of interpolation as a string ('linear', 'nearest',
        'zero', 'slinear', 'quadratic, 'cubic') or as an integer specifying the
        order of the spline interpolator to use.


    Returns
    -------
    v, e : tuple,
        v is an array of DPSS windows shaped (Kmax, N)
        e are the eigenvalues

    Notes
    -----
    Tridiagonal form of DPSS calculation from:

    Slepian, D. Prolate spheroidal wave functions, Fourier analysis, and
    uncertainty V: The discrete case. Bell System Technical Journal,
    Volume 57 (1978), 1371430
    """
    Kmax = int(Kmax)
    W = float(NW) / N
    nidx = np.arange(N, dtype='d')

    # In this case, we create the dpss windows of the smaller size
    # (interp_from) and then interpolate to the larger size (N)
    if interp_from is not None:
        if interp_from > N:
            e_s = 'In dpss_windows, interp_from is: %s ' % interp_from
            e_s += 'and N is: %s. ' % N
            e_s += 'Please enter interp_from smaller than N.'
            raise ValueError(e_s)
        dpss = [ ]
        d, e = dpss_windows(interp_from, NW, Kmax)
        for this_d in d:
            x = np.arange(this_d.shape[ -1 ])
            I = interpolate.interp1d(x, this_d, kind=interp_kind)
            d_temp = I(np.arange(0, this_d.shape[ -1 ] - 1,
                                 float(this_d.shape[ -1 ] - 1) / N))

            # Rescale:
            d_temp = d_temp / np.sqrt(np.sum(d_temp ** 2))

            dpss.append(d_temp)

        dpss = np.array(dpss)

    else:
        # here we want to set up an optimization problem to find a sequence
        # whose energy is maximally concentrated within band [-W,W].
        # Thus, the measure lambda(T,W) is the ratio between the energy within
        # that band, and the total energy. This leads to the eigen-system
        # (A - (l1)I)v = 0, where the eigenvector corresponding to the largest
        # eigenvalue is the sequence with maximally concentrated energy. The
        # collection of eigenvectors of this system are called Slepian
        # sequences, or discrete prolate spheroidal sequences (DPSS). Only the
        # first K, K = 2NW/dt orders of DPSS will exhibit good spectral
        # concentration
        # [see http://en.wikipedia.org/wiki/Spectral_concentration_problem]

        # Here I set up an alternative symmetric tri-diagonal eigenvalue
        # problem such that
        # (B - (l2)I)v = 0, and v are our DPSS (but eigenvalues l2 != l1)
        # the main diagonal = ([N-1-2*t]/2)**2 cos(2PIW), t=[0,1,2,...,N-1]
        # and the first off-diagonal = t(N-t)/2, t=[1,2,...,N-1]
        # [see Percival and Walden, 1993]
        diagonal = ((N - 1 - 2 * nidx) / 2.) ** 2 * np.cos(2 * np.pi * W)
        off_diag = np.zeros_like(nidx)
        off_diag[ :-1 ] = nidx[ 1: ] * (N - nidx[ 1: ]) / 2.
        # put the diagonals in LAPACK "packed" storage
        ab = np.zeros((2, N), 'd')
        ab[ 1 ] = diagonal
        ab[ 0, 1: ] = off_diag[ :-1 ]
        # only calculate the highest Kmax eigenvalues
        w = linalg.eigvals_banded(ab, select='i',
                                  select_range=(N - Kmax, N - 1))
        w = w[ ::-1 ]

        # find the corresponding eigenvectors via inverse iteration
        t = np.linspace(0, np.pi, N)
        dpss = np.zeros((Kmax, N), 'd')
        for k in range(Kmax):
            dpss[ k ] = utils._tridi_inverse_iteration(
                diagonal, off_diag, w[ k ], x0=np.sin((k + 1) * t)
            )

    # By convention (Percival and Walden, 1993 pg 379)
    # * symmetric tapers (k=0,2,4,...) should have a positive average.
    # * antisymmetric tapers should begin with a positive lobe
    fix_symmetric = (dpss[ 0::2 ].sum(axis=1) < 0)
    for i, f in enumerate(fix_symmetric):
        if f:
            dpss[ 2 * i ] *= -1
    # rather than test the sign of one point, test the sign of the
    # linear slope up to the first (largest) peak
    pk = np.argmax(np.abs(dpss[ 1::2, :N // 2 ]), axis=1)
    for i, p in enumerate(pk):
        if np.sum(dpss[ 2 * i + 1, :p ]) < 0:
            dpss[ 2 * i + 1 ] *= -1

    # Now find the eigenvalues of the original spectral concentration problem
    # Use the autocorr sequence technique from Percival and Walden, 1993 pg 390
    dpss_rxx = utils.autocorr(dpss) * N
    r = 4 * W * np.sinc(2 * W * nidx)
    r[ 0 ] = 2 * W
    eigvals = np.dot(dpss_rxx, r)

    return dpss, eigvals


def tapered_spectra(s, tapers, NFFT=None, low_bias=True):
    """
    Compute the tapered spectra of the rows of s.

    Parameters
    ----------

    s : ndarray, (n_arr, n_pts)
        An array whose rows are timeseries.

    tapers : ndarray or container
        Either the precomputed DPSS tapers, or the pair of parameters
        (NW, K) needed to compute K tapers of length n_pts.

    NFFT : int
        Number of FFT bins to compute

    low_bias : Boolean
        If compute DPSS, automatically select tapers corresponding to
        > 90% energy concentration.

    Returns
    -------

    t_spectra : ndarray, shaped (n_arr, K, NFFT)
      The FFT of the tapered sequences in s. First dimension is squeezed
      out if n_arr is 1.
    eigvals : ndarray
      The eigenvalues are also returned if DPSS are calculated here.

    """
    N = s.shape[ -1 ]
    # XXX: don't allow NFFT < N -- not every implementation is so restrictive!
    if NFFT is None or NFFT < N:
        if NFFT is not None:
            warnings.warn('More NFFT bins to compute than datapoints',
                          UserWarning)
        NFFT = N
    rest_of_dims = s.shape[ :-1 ]
    M = int(np.product(rest_of_dims))

    s = s.reshape(int(np.product(rest_of_dims)), N)
    # de-mean this sucker
    s = utils._remove_bias(s, axis=-1)

    if not isinstance(tapers, np.ndarray):
        # then tapers is (NW, K)
        args = (N,) + tuple(tapers)
        dpss, eigvals = dpss_windows(*args)
        if low_bias:
            keepers = (eigvals > 0.9)
            dpss = dpss[ keepers ]
            eigvals = eigvals[ keepers ]
        tapers = dpss
    else:
        eigvals = None
    K = tapers.shape[ 0 ]
    sig_sl = [ slice(None) ] * len(s.shape)
    sig_sl.insert(len(s.shape) - 1, np.newaxis)

    # tapered.shape is (M, Kmax, N)
    tapered = s[ sig_sl ] * tapers

    # compute the y_{i,k}(f) -- full FFT takes ~1.5x longer, but unpacking
    # results of real-valued FFT eats up memory
    t_spectra = fftpack.fft(tapered, n=NFFT, axis=-1)
    t_spectra.shape = rest_of_dims + (K, NFFT)
    if eigvals is None:
        return t_spectra
    return t_spectra, eigvals


def mtm_cross_spectrum(tx, ty, weights, sides='twosided'):
    r"""

    The cross-spectrum between two tapered time-series, derived from a
    multi-taper spectral estimation.

    Parameters
    ----------

    tx, ty : ndarray (K, ..., N)
       The complex DFTs of the tapered sequence

    weights : ndarray, or 2-tuple or list
       Weights can be specified as a length-2 list of weights for spectra tx
       and ty respectively. Alternatively, if tx is ty and this function is
       computing the spectral density function of a single sequence, the
       weights can be given as an ndarray of weights for the spectrum.
       Weights may be

       * scalars, if the shape of the array is (K, ..., 1)
       * vectors, with the shape of the array being the same as tx or ty

    sides : str in {'onesided', 'twosided'}
       For the symmetric spectra of a real sequence, optionally combine half
       of the frequencies and scale the duplicate frequencies in the range
       (0, F_nyquist).

    Notes
    -----

    spectral densities are always computed as

    :math:`S_{xy}^{mt}(f) = \frac{\sum_k
    [d_k^x(f)s_k^x(f)][d_k^y(f)(s_k^y(f))^{*}]}{[\sum_k
    d_k^x(f)^2]^{\frac{1}{2}}[\sum_k d_k^y(f)^2]^{\frac{1}{2}}}`

    """
    N = tx.shape[ -1 ]
    if ty.shape != tx.shape:
        raise ValueError('shape mismatch between tx, ty')

    if isinstance(weights, (list, tuple)):
        autospectrum = False
        weights_x = weights[ 0 ]
        weights_y = weights[ 1 ]
        denom = (np.abs(weights_x) ** 2).sum(axis=0) ** 0.5
        denom *= (np.abs(weights_y) ** 2).sum(axis=0) ** 0.5
    else:
        autospectrum = True
        weights_x = weights
        weights_y = weights
        denom = (np.abs(weights) ** 2).sum(axis=0)

    if sides == 'onesided':
        # where the nyq freq should be
        Fn = N // 2 + 1
        truncated_slice = [ slice(None) ] * len(tx.shape)
        truncated_slice[ -1 ] = slice(0, Fn)
        tsl = tuple(truncated_slice)
        tx = tx[ tsl ]
        ty = ty[ tsl ]
        # if weights.shape[-1] > 1 then make sure weights are truncated too
        if weights_x.shape[ -1 ] > 1:
            weights_x = weights_x[ tsl ]
            weights_y = weights_y[ tsl ]
            denom = denom[ tsl[ 1: ] ]

    sf = weights_x * tx
    sf *= (weights_y * ty).conj()
    sf = sf.sum(axis=0)
    sf /= denom

    if sides == 'onesided':
        # dbl power at duplicated freqs
        Fl = (N + 1) // 2
        sub_slice = [ slice(None) ] * len(sf.shape)
        sub_slice[ -1 ] = slice(1, Fl)
        sf[ tuple(sub_slice) ] *= 2

    if autospectrum:
        return sf.real
    return sf


def multi_taper_psd(
        s, Fs=2 * np.pi, NW=None, BW=None, adaptive=False,
        jackknife=True, low_bias=True, sides='default', NFFT=None
):
    """Returns an estimate of the PSD function of s using the multitaper
    method. If the NW product, or the BW and Fs in Hz are not specified
    by the user, a bandwidth of 4 times the fundamental frequency,
    corresponding to NW = 4 will be used.

    Parameters
    ----------
    s : ndarray
       An array of sampled random processes, where the time axis is assumed to
       be on the last axis

    Fs : float
        Sampling rate of the signal

    NW : float
        The normalized half-bandwidth of the data tapers, indicating a
        multiple of the fundamental frequency of the DFT (Fs/N).
        Common choices are n/2, for n >= 4. This parameter is unitless
        and more MATLAB compatible. As an alternative, set the BW
        parameter in Hz. See Notes on bandwidth.

    BW : float
        The sampling-relative bandwidth of the data tapers, in Hz.

    adaptive : {True/False}
       Use an adaptive weighting routine to combine the PSD estimates of
       different tapers.

    jackknife : {True/False}
       Use the jackknife method to make an estimate of the PSD variance
       at each point.

    low_bias : {True/False}
       Rather than use 2NW tapers, only use the tapers that have better than
       90% spectral concentration within the bandwidth (still using
       a maximum of 2NW tapers)

    sides : str (optional)   [ 'default' | 'onesided' | 'twosided' ]
         This determines which sides of the spectrum to return.
         For complex-valued inputs, the default is two-sided, for real-valued
         inputs, default is one-sided Indicates whether to return a one-sided
         or two-sided

    Returns
    -------
    (freqs, psd_est, var_or_nu) : ndarrays
        The first two arrays are the frequency points vector and the
        estimated PSD. The last returned array differs depending on whether
        the jackknife was used. It is either

        * The jackknife estimated variance of the log-psd, OR
        * The degrees of freedom in a chi2 model of how the estimated
          PSD is distributed about the true log-PSD (this is either
          2*floor(2*NW), or calculated from adaptive weights)

    Notes
    -----

    The bandwidth of the windowing function will determine the number
    tapers to use. This parameters represents trade-off between frequency
    resolution (lower main lobe BW for the taper) and variance reduction
    (higher BW and number of averaged estimates). Typically, the number of
    tapers is calculated as 2x the bandwidth-to-fundamental-frequency
    ratio, as these eigenfunctions have the best energy concentration.

    """
    # have last axis be time series for now
    N = s.shape[ -1 ]
    M = int(np.product(s.shape[ :-1 ]))

    if BW is not None:
        # BW wins in a contest (since it was the original implementation)
        norm_BW = np.round(BW * N / Fs)
        NW = norm_BW / 2.0
    elif NW is None:
        # default NW
        NW = 4
    # (else BW is None and NW is not None) ... all set
    Kmax = int(2 * NW)

    # if the time series is a complex vector, a one sided PSD is invalid:
    if (sides == 'default' and np.iscomplexobj(s)) or sides == 'twosided':
        sides = 'twosided'
    elif sides in ('default', 'onesided'):
        sides = 'onesided'

    # Find the direct spectral estimators S_k(f) for k tapered signals..
    # don't normalize the periodograms by 1/N as normal.. since the taper
    # windows are orthonormal, they effectively scale the signal by 1/N
    spectra, eigvals = tapered_spectra(
        s, (NW, Kmax), NFFT=NFFT, low_bias=low_bias
    )
    NFFT = spectra.shape[ -1 ]
    K = len(eigvals)
    # collapse spectra's shape back down to 3 dimensions
    spectra.shape = (M, K, NFFT)

    last_freq = NFFT // 2 + 1 if sides == 'onesided' else NFFT

    # degrees of freedom at each timeseries, at each freq
    nu = np.empty((M, last_freq))
    if adaptive:
        weights = np.empty((M, K, last_freq))
        for i in range(M):
            weights[ i ], nu[ i ] = utils._adaptive_weights(
                spectra[ i ], eigvals, sides=sides
            )
    else:
        # let the weights simply be the square-root of the eigenvalues.
        # repeat these values across all n_chan channels of data
        weights = np.tile(np.sqrt(eigvals), M).reshape(M, K, 1)
        nu.fill(2 * K)

    if jackknife:
        jk_var = np.empty_like(nu)
        for i in range(M):
            jk_var[ i ] = utils.jackknifed_sdf_variance(
                spectra[ i ], eigvals, sides=sides, adaptive=adaptive
            )

    # Compute the unbiased spectral estimator for S(f) as the sum of
    # the S_k(f) weighted by the function w_k(f)**2, all divided by the
    # sum of the w_k(f)**2 over k

    # 1st, roll the tapers axis forward
    spectra = np.rollaxis(spectra, 1, start=0)
    weights = np.rollaxis(weights, 1, start=0)
    sdf_est = mtm_cross_spectrum(
        spectra, spectra, weights, sides=sides
    )
    sdf_est /= Fs

    if sides == 'onesided':
        freqs = np.linspace(0, Fs / 2, NFFT / 2 + 1)
    else:
        freqs = np.linspace(0, Fs, NFFT, endpoint=False)

    out_shape = s.shape[ :-1 ] + (len(freqs),)
    sdf_est.shape = out_shape
    if jackknife:
        jk_var.shape = out_shape
        return freqs, sdf_est, jk_var
    else:
        nu.shape = out_shape
        return freqs, sdf_est, nu


def multi_taper_csd(s, Fs=2 * np.pi, NW=None, BW=None, low_bias=True,
                    adaptive=False, sides='default', NFFT=None):
    """Returns an estimate of the Cross Spectral Density (CSD) function
    between all (N choose 2) pairs of timeseries in s, using the multitaper
    method. If the NW product, or the BW and Fs in Hz are not specified by
    the user, a bandwidth of 4 times the fundamental frequency, corresponding
    to NW = 4 will be used.

    Parameters
    ----------
    s : ndarray
        An array of sampled random processes, where the time axis is
        assumed to be on the last axis. If ndim > 2, the number of time
        series to compare will still be taken as prod(s.shape[:-1])

    Fs : float, Sampling rate of the signal

    NW : float
        The normalized half-bandwidth of the data tapers, indicating a
        multiple of the fundamental frequency of the DFT (Fs/N).
        Common choices are n/2, for n >= 4. This parameter is unitless
        and more MATLAB compatible. As an alternative, set the BW
        parameter in Hz. See Notes on bandwidth.

    BW : float
        The sampling-relative bandwidth of the data tapers, in Hz.

    adaptive : {True, False}
       Use adaptive weighting to combine spectra

    low_bias : {True, False}
       Rather than use 2NW tapers, only use the tapers that have better than
       90% spectral concentration within the bandwidth (still using
       a maximum of 2NW tapers)

    sides : str (optional)   [ 'default' | 'onesided' | 'twosided' ]
         This determines which sides of the spectrum to return.  For
         complex-valued inputs, the default is two-sided, for real-valued
         inputs, default is one-sided Indicates whether to return a one-sided
         or two-sided

    Returns
    -------
    (freqs, csd_est) : ndarrays
        The estimatated CSD and the frequency points vector.
        The CSD{i,j}(f) are returned in a square "matrix" of vectors
        holding Sij(f). For an input array of (M,N), the output is (M,M,N)

    Notes
    -----

    The bandwidth of the windowing function will determine the number
    tapers to use. This parameters represents trade-off between frequency
    resolution (lower main lobe BW for the taper) and variance reduction
    (higher BW and number of averaged estimates). Typically, the number of
    tapers is calculated as 2x the bandwidth-to-fundamental-frequency
    ratio, as these eigenfunctions have the best energy concentration.

    """
    # have last axis be time series for now
    N = s.shape[ -1 ]
    M = int(np.product(s.shape[ :-1 ]))

    if BW is not None:
        # BW wins in a contest (since it was the original implementation)
        norm_BW = np.round(BW * N / Fs)
        NW = norm_BW / 2.0
    elif NW is None:
        # default NW
        NW = 4
    # (else BW is None and NW is not None) ... all set
    Kmax = int(2 * NW)

    # if the time series is a complex vector, a one sided PSD is invalid:
    if (sides == 'default' and np.iscomplexobj(s)) or sides == 'twosided':
        sides = 'twosided'
    elif sides in ('default', 'onesided'):
        sides = 'onesided'

    # Find the direct spectral estimators S_k(f) for k tapered signals..
    # don't normalize the periodograms by 1/N as normal.. since the taper
    # windows are orthonormal, they effectively scale the signal by 1/N
    spectra, eigvals = tapered_spectra(
        s, (NW, Kmax), NFFT=NFFT, low_bias=low_bias
    )
    NFFT = spectra.shape[ -1 ]
    K = len(eigvals)
    # collapse spectra's shape back down to 3 dimensions
    spectra.shape = (M, K, NFFT)

    # compute the cross-spectral density functions
    last_freq = NFFT // 2 + 1 if sides == 'onesided' else NFFT

    if adaptive:
        w = np.empty((M, K, last_freq))
        nu = np.empty((M, last_freq))
        for i in range(M):
            w[ i ], nu[ i ] = utils._adaptive_weights(
                spectra[ i ], eigvals, sides=sides
            )
    else:
        weights = np.sqrt(eigvals).reshape(K, 1)

    csd_pairs = np.zeros((M, M, last_freq), 'D')
    for i in range(M):
        if adaptive:
            wi = w[ i ]
        else:
            wi = weights
        for j in range(i + 1):
            if adaptive:
                wj = w[ j ]
            else:
                wj = weights
            ti = spectra[ i ]
            tj = spectra[ j ]
            csd_pairs[ i, j ] = mtm_cross_spectrum(ti, tj, (wi, wj),
                                                   sides=sides)

    csdfs = csd_pairs.transpose(1, 0, 2).conj()
    csdfs += csd_pairs
    diag_idc = (np.arange(M), np.arange(M))
    csdfs[ diag_idc ] /= 2
    csdfs /= Fs

    if sides == 'onesided':
        freqs = np.linspace(0, Fs / 2, NFFT / 2 + 1)
    else:
        freqs = np.linspace(0, Fs, NFFT, endpoint=False)

    return freqs, csdfs


def freq_response(b, a=1., n_freqs=1024, sides='onesided'):
    """
    Returns the frequency response of the IIR or FIR filter described
    by beta and alpha coefficients.

    Parameters
    ----------

    b : beta sequence (moving average component)
    a : alpha sequence (autoregressive component)
    n_freqs : size of frequency grid
    sides : {'onesided', 'twosided'}
       compute frequencies between [-PI,PI), or from [0, PI]

    Returns
    -------

    fgrid, H(e^jw)

    Notes
    -----
    For a description of the linear constant-coefficient difference equation,
    see
    http://en.wikipedia.org/wiki/Z-transform
    """
    # transitioning to scipy freqz
    real_n = n_freqs // 2 + 1 if sides == 'onesided' else n_freqs
    return sig.freqz(b, a=a, worN=real_n, whole=sides != 'onesided')
