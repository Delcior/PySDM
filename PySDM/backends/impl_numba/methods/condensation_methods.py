"""
CPU implementation of backend methods for water condensation/evaporation
"""
import math
from functools import lru_cache
import numpy as np
import numba
from PySDM.backends.impl_numba import conf
from PySDM.backends.impl_numba.toms748 import toms748_solve
from PySDM.backends.impl_common.backend_methods import BackendMethods
from PySDM.backends.impl_numba.warnings import warn


class CondensationMethods(BackendMethods):
    # pylint: disable=unused-argument
    @staticmethod
    def condensation(
            solver,
            n_cell, cell_start_arg,
            v, v_cr, n, vdry, idx, rhod, thd, qv, dv, prhod, pthd, pqv, kappa, f_org,
            rtol_x, rtol_thd, timestep, counters, cell_order, RH_max, success, cell_id
    ):
        n_threads = min(numba.get_num_threads(), n_cell)
        CondensationMethods._condensation(
            solver, n_threads, n_cell, cell_start_arg.data, v.data, v_cr.data, n.data,
            vdry.data, idx.data, rhod.data, thd.data, qv.data, dv, prhod.data, pthd.data,
            pqv.data, kappa.data, f_org.data, rtol_x, rtol_thd, timestep,
            counters['n_substeps'].data,
            counters['n_activating'].data,
            counters['n_deactivating'].data,
            counters['n_ripening'].data,
            cell_order, RH_max.data, success.data
        )

    @staticmethod
    @numba.njit(**{**conf.JIT_FLAGS, **{'cache': False}})
    def _condensation(
            solver, n_threads, n_cell, cell_start_arg,
            v, v_cr, n, vdry, idx, rhod, thd, qv, dv_mean, prhod, pthd, pqv, kappa, f_org,
            rtol_x, rtol_thd, timestep,
            counter_n_substeps, counter_n_activating, counter_n_deactivating, counter_n_ripening,
            cell_order, RH_max, success
    ):
        for thread_id in numba.prange(n_threads):  # pylint: disable=not-an-iterable
            for i in range(thread_id, n_cell, n_threads):
                cell_id = cell_order[i]

                cell_start = cell_start_arg[cell_id]
                cell_end = cell_start_arg[cell_id + 1]
                n_sd_in_cell = cell_end - cell_start
                if n_sd_in_cell == 0:
                    continue

                dthd_dt = (pthd[cell_id] - thd[cell_id]) / timestep
                dqv_dt = (pqv[cell_id] - qv[cell_id]) / timestep
                rhod_mean = (prhod[cell_id] + rhod[cell_id]) / 2
                md = rhod_mean * dv_mean

                success_in_cell, qv_new, thd_new, substeps_hint, \
                    n_activating, n_deactivating, n_ripening, RH_max_in_cell = solver(
                        v, v_cr, n, vdry,
                        idx[cell_start:cell_end],
                        kappa, f_org, thd[cell_id], qv[cell_id], dthd_dt, dqv_dt, md, rhod_mean,
                        rtol_x, rtol_thd, timestep, counter_n_substeps[cell_id]
                    )
                counter_n_substeps[cell_id] = substeps_hint
                counter_n_activating[cell_id] = n_activating
                counter_n_deactivating[cell_id] = n_deactivating
                counter_n_ripening[cell_id] = n_ripening
                RH_max[cell_id] = RH_max_in_cell
                success[cell_id] = success_in_cell
                pqv[cell_id] = qv_new
                pthd[cell_id] = thd_new

    @staticmethod
    def make_adapt_substeps(
        jit_flags, timestep, step_fake, dt_range, fuse, multiplier, within_tolerance
    ):
        if not isinstance(multiplier, int):
            raise ValueError()
        if dt_range[1] > timestep:
            dt_range = (dt_range[0], timestep)
        if dt_range[0] == 0:
            raise NotImplementedError()
        n_substeps_max = math.floor(timestep / dt_range[0])
        n_substeps_min = math.ceil(timestep / dt_range[1])

        @numba.njit(**jit_flags)
        def adapt_substeps(args, n_substeps, thd, rtol_thd):
            n_substeps = np.maximum(n_substeps_min, n_substeps // multiplier)
            success = False
            for burnout in range(fuse + 1):
                if burnout == fuse:
                    return warn(
                        "burnout (long)",
                        __file__,
                        context=("thd", thd,),
                        return_value=(0, False)
                    )
                thd_new_long, success = step_fake(args, timestep, n_substeps)
                if success:
                    break
                n_substeps *= multiplier
            for burnout in range(fuse + 1):
                if burnout == fuse:
                    return warn("burnout (short)", __file__, return_value=(0, False))
                thd_new_short, success = step_fake(args, timestep, n_substeps * multiplier)
                if not success:
                    return warn("short failed", __file__, return_value=(0, False))
                dthd_long = thd_new_long - thd
                dthd_short = thd_new_short - thd
                error_estimate = np.abs(dthd_long - multiplier * dthd_short)
                thd_new_long = thd_new_short
                if within_tolerance(error_estimate, thd, rtol_thd):
                    break
                n_substeps *= multiplier
                if n_substeps > n_substeps_max:
                    break
            return np.minimum(n_substeps_max, n_substeps), success

        return adapt_substeps

    @staticmethod
    def make_step_fake(jit_flags, step_impl):
        @numba.njit(**jit_flags)
        def step_fake(args, dt, n_substeps):
            dt /= n_substeps
            _, thd_new, _, _, _, _, success = step_impl(*args, dt, 1, True)
            return thd_new, success

        return step_fake

    @staticmethod
    def make_step(jit_flags, step_impl):
        @numba.njit(**jit_flags)
        def step(args, dt, n_substeps):
            return step_impl(*args, dt, n_substeps, False)

        return step

    @staticmethod
    def make_step_impl(
        jit_flags, phys_pvs_C, phys_lv, calculate_ml_old, calculate_ml_new, phys_T,
        phys_p, phys_pv, phys_dthd_dt, phys_D, const
    ):
        @numba.njit(**jit_flags)
        def step_impl(
            v, v_cr, n, vdry, cell_idx, kappa, f_org, thd, qv, dthd_dt_pred, dqv_dt_pred,
            m_d, rhod_mean, rtol_x, timestep, n_substeps, fake
        ):
            timestep /= n_substeps
            ml_old = calculate_ml_old(v, n, cell_idx)
            count_activating, count_deactivating, count_ripening = 0, 0, 0
            RH_max = 0
            success = True
            for _ in range(n_substeps):
                # note: no example yet showing that the trapezoidal scheme brings any improvement
                thd += timestep * dthd_dt_pred / 2
                qv += timestep * dqv_dt_pred / 2

                T = phys_T(rhod_mean, thd)
                p = phys_p(rhod_mean, T, qv)
                pv = phys_pv(p, qv)
                lv = phys_lv(T)
                pvs = phys_pvs_C(T - const.T0)
                RH = pv / pvs
                DTp = phys_D(T, p)
                ml_new, success_within_substep, n_activating, n_deactivating, n_ripening = \
                    calculate_ml_new(
                        timestep, fake, T, p, RH, v, v_cr, n, vdry, cell_idx,
                        kappa, f_org, lv, pvs, DTp, rtol_x
                    )
                dml_dt = (ml_new - ml_old) / timestep
                dqv_dt_corr = - dml_dt / m_d
                dthd_dt_corr = phys_dthd_dt(rhod=rhod_mean, thd=thd, T=T, dqv_dt=dqv_dt_corr, lv=lv)

                thd += timestep * (dthd_dt_pred / 2 + dthd_dt_corr)
                qv += timestep * (dqv_dt_pred / 2 + dqv_dt_corr)
                ml_old = ml_new
                count_activating += n_activating
                count_deactivating += n_deactivating
                count_ripening += n_ripening
                RH_max = max(RH_max, RH)
                success = success and success_within_substep
            return qv, thd, count_activating, count_deactivating, count_ripening, RH_max, success

        return step_impl

    @staticmethod
    def make_calculate_ml_old(jit_flags, const):
        @numba.njit(**jit_flags)
        def calculate_ml_old(volume, multiplicity, cell_idx):
            result = 0
            for drop in cell_idx:
                if volume[drop] > 0:
                    result += multiplicity[drop] * volume[drop] * const.rho_w
            return result

        return calculate_ml_old

    @staticmethod
    def make_calculate_ml_new(
        jit_flags, dx_dt, volume_of_x, x, phys_r_dr_dt, phys_RH_eq, phys_sigma, radius,
        phys_lambdaK, phys_lambdaD, phys_dk_D, phys_dk_K, within_tolerance, max_iters, RH_rtol,
        const
    ):
        @numba.njit(**jit_flags)
        def minfun(x_new, x_old, timestep, kappa, f_org, rd3, temperature, RH, lv, pvs, D, K):
            volume = volume_of_x(x_new)
            RH_eq = phys_RH_eq(
                radius(volume),
                temperature,
                kappa,
                rd3,
                phys_sigma(temperature, volume, const.PI_4_3 * rd3, f_org)
            )
            r_dr_dt = phys_r_dr_dt(RH_eq, temperature, RH, lv, pvs, D, K)
            return x_old - x_new + timestep * dx_dt(x_new, r_dr_dt)

        @numba.njit(**jit_flags)
        def calculate_ml_new(
            timestep, fake, T, p, RH, v, v_cr, n, vdry, cell_idx,
            kappa, f_org, lv, pvs, DTp, rtol_x
        ):
            result = 0
            n_activating = 0
            n_deactivating = 0
            n_activated_and_growing = 0
            success = True
            lambdaK = phys_lambdaK(T, p)
            lambdaD = phys_lambdaD(DTp, T)
            for drop in cell_idx:
                if v[drop] < 0:
                    continue
                x_old = x(v[drop])
                r_old = radius(v[drop])
                x_insane = x(vdry[drop]/100)
                rd3 = vdry[drop] / const.PI_4_3
                sgm = phys_sigma(T, v[drop], vdry[drop], f_org[drop])
                RH_eq = phys_RH_eq(r_old, T, kappa[drop], rd3, sgm)
                if not within_tolerance(np.abs(RH - RH_eq), RH, RH_rtol):
                    Dr = phys_dk_D(DTp, r_old, lambdaD)
                    Kr = phys_dk_K(const.K0, r_old, lambdaK)
                    args = (x_old, timestep, kappa[drop], f_org[drop], rd3, T, RH, lv, pvs, Dr, Kr)
                    r_dr_dt_old = phys_r_dr_dt(RH_eq, T, RH, lv, pvs, Dr, Kr)
                    dx_old = timestep * dx_dt(x_old, r_dr_dt_old)
                else:
                    dx_old = 0.
                if dx_old == 0:
                    x_new = x_old
                else:
                    a = x_old
                    b = max(x_insane, a + dx_old)
                    fa = minfun(a, *args)
                    fb = minfun(b, *args)

                    counter = 0
                    while not fa * fb < 0:
                        counter += 1
                        if counter > max_iters:
                            if not fake:
                                warn(
                                    "failed to find interval", __file__,
                                    context=(
                                        "T", T,
                                        "p", p,
                                        "RH", RH,
                                        "a", a,
                                        "b", b,
                                        "fa", fa,
                                        "fb", fb
                                    )
                                )
                            success = False
                            break
                        b = max(x_insane, a + math.ldexp(dx_old, counter))
                        fb = minfun(b, *args)

                    if not success:
                        break
                    if a != b:
                        if a > b:
                            a, b = b, a
                            fa, fb = fb, fa

                        x_new, iters_taken = toms748_solve(
                            minfun, args, a, b, fa, fb, rtol_x, max_iters, within_tolerance
                        )
                        if iters_taken in (-1, max_iters):
                            if not fake:
                                warn("TOMS failed", __file__)
                            success = False
                            break
                    else:
                        x_new = x_old

                v_new = volume_of_x(x_new)
                result += n[drop] * v_new * const.rho_w
                if not fake:
                    if v_new > v_cr[drop] and v_new > v[drop]:
                        n_activated_and_growing += n[drop]
                    if v_new > v_cr[drop] > v[drop]:
                        n_activating += n[drop]
                    if v_new < v_cr[drop] < v[drop]:
                        n_deactivating += n[drop]
                    v[drop] = v_new
            n_ripening = n_activated_and_growing if n_deactivating > 0 else 0
            return result, success, n_activating, n_deactivating, n_ripening

        return calculate_ml_new

    # pylint disable=unused-argument
    def make_condensation_solver(self,
                                 timestep, n_cell, *, dt_range, adaptive, fuse,
                                 multiplier, RH_rtol, max_iters):
        return CondensationMethods.make_condensation_solver_impl(
            fastmath=self.formulae.fastmath,
            phys_pvs_C=self.formulae.saturation_vapour_pressure.pvs_Celsius,
            phys_lv=self.formulae.latent_heat.lv,
            phys_r_dr_dt=self.formulae.drop_growth.r_dr_dt,
            phys_RH_eq=self.formulae.hygroscopicity.RH_eq,
            phys_sigma=self.formulae.surface_tension.sigma,
            radius=self.formulae.trivia.radius,
            phys_T=self.formulae.state_variable_triplet.T,
            phys_p=self.formulae.state_variable_triplet.p,
            phys_pv=self.formulae.state_variable_triplet.pv,
            phys_dthd_dt=self.formulae.state_variable_triplet.dthd_dt,
            phys_lambdaK=self.formulae.diffusion_kinetics.lambdaK,
            phys_lambdaD=self.formulae.diffusion_kinetics.lambdaD,
            phys_dk_D=self.formulae.diffusion_kinetics.D,
            phys_dk_K=self.formulae.diffusion_kinetics.K,
            phys_D=self.formulae.diffusion_thermics.D,
            within_tolerance=self.formulae.trivia.within_tolerance,
            dx_dt=self.formulae.condensation_coordinate.dx_dt,
            volume=self.formulae.condensation_coordinate.volume,
            x=self.formulae.condensation_coordinate.x,
            timestep=timestep,
            dt_range=dt_range,
            adaptive=adaptive,
            fuse=fuse,
            multiplier=multiplier,
            RH_rtol=RH_rtol,
            max_iters=max_iters,
            const=self.formulae.constants
        )

    @staticmethod
    @lru_cache()
    def make_condensation_solver_impl(
        fastmath, phys_pvs_C, phys_lv, phys_r_dr_dt, phys_RH_eq, phys_sigma, radius,
        phys_T, phys_p, phys_pv, phys_dthd_dt, phys_lambdaK, phys_lambdaD, phys_dk_D, phys_dk_K,
        phys_D, within_tolerance, dx_dt, volume, x, timestep, dt_range, adaptive,
        fuse, multiplier, RH_rtol, max_iters, const
    ):
        jit_flags = {**conf.JIT_FLAGS, **{'parallel': False, 'cache': False, 'fastmath': fastmath}}

        calculate_ml_old = CondensationMethods.make_calculate_ml_old(jit_flags, const)
        calculate_ml_new = CondensationMethods.make_calculate_ml_new(
            jit_flags, dx_dt, volume, x, phys_r_dr_dt, phys_RH_eq, phys_sigma, radius,
            phys_lambdaK, phys_lambdaD, phys_dk_D, phys_dk_K, within_tolerance, max_iters, RH_rtol,
            const
        )
        step_impl = CondensationMethods.make_step_impl(
            jit_flags, phys_pvs_C, phys_lv, calculate_ml_old, calculate_ml_new,
            phys_T, phys_p, phys_pv, phys_dthd_dt, phys_D, const
        )
        step_fake = CondensationMethods.make_step_fake(jit_flags, step_impl)
        adapt_substeps = CondensationMethods.make_adapt_substeps(
            jit_flags, timestep, step_fake, dt_range, fuse, multiplier, within_tolerance
        )
        step = CondensationMethods.make_step(jit_flags, step_impl)

        @numba.njit(**jit_flags)
        def solve(v, v_cr, n, vdry, cell_idx, kappa, f_org, thd, qv, dthd_dt, dqv_dt,
                  m_d, rhod_mean, rtol_x, rtol_thd, timestep, n_substeps):
            args = (
                v, v_cr, n, vdry, cell_idx, kappa, f_org, thd, qv,
                dthd_dt, dqv_dt, m_d, rhod_mean, rtol_x
            )
            success = True
            if adaptive:
                n_substeps, success = adapt_substeps(args, n_substeps, thd, rtol_thd)
            if success:
                qv, thd, n_activating, n_deactivating, n_ripening, RH_max, success = step(
                    args, timestep, n_substeps
                )
            else:
                n_activating, n_deactivating, n_ripening, RH_max = -1, -1, -1, -1
            return success, qv, thd, n_substeps, n_activating, n_deactivating, n_ripening, RH_max

        return solve
