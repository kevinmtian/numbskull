"""TODO."""

from __future__ import print_function
import numba
from numba import jit
import numpy as np
import math


@jit(nopython=True, cache=True, nogil=True)
def gibbsthread(shardID, nshards, var_copy, weight_copy, weight, variable,
                factor, fmap, vmap, factor_index, Z, cstart,
                count, var_value, weight_value, sample_evidence, burnin):
    """TODO."""
    # Indentify start and end variable
    nvar = variable.shape[0]
    start = (shardID * nvar) // nshards
    end = ((shardID + 1) * nvar) // nshards
    Z = Z.copy()
    # TODO: give option do not store result, or just store tally
    for var_samp in range(start, end):
        if variable[var_samp]["isEvidence"] == 0 or sample_evidence:
            v = draw_sample(var_samp, var_copy, weight_copy, weight, variable,
                            factor, fmap, vmap, factor_index, Z,
                            var_value, weight_value)
            var_value[var_copy][var_samp] = v
            if not burnin:
                if variable[var_samp]["dataType"] == 0:
                    count[cstart[var_samp]] += v
                else:
                    count[cstart[var_samp] + v] += 1


@jit(nopython=True, cache=True, nogil=True)
def draw_sample(var_samp, var_copy, weight_copy, weight, variable, factor,
                fmap, vmap, factor_index, Z, var_value, weight_value):
    """TODO."""
    cardinality = variable[var_samp]["cardinality"]
    for value in range(cardinality):
        Z[value] = np.exp(potential(var_samp, value, var_copy, weight_copy,
                                    weight, variable, factor, fmap,
                                    vmap, factor_index, var_value,
                                    weight_value))

    for j in range(1, cardinality):
        Z[j] += Z[j - 1]

    z = np.random.rand() * Z[cardinality - 1]

    # TODO: this looks at the full vector, slow if one var has high cardinality
    return np.argmax(Z >= z)


@jit(nopython=True, cache=True, nogil=True)
def potential(var_samp, value, var_copy, weight_copy, weight, variable, factor,
              fmap, vmap, factor_index, var_value, weight_value):
    """TODO."""
    p = 0.0
    varval_off = value
    if variable[var_samp]["dataType"] == 0:
        varval_off = 0
    vtf = vmap[variable[var_samp]["vtf_offset"] + varval_off]
    start = vtf["factor_index_offset"]
    end = start + vtf["factor_index_length"]
    for k in range(start, end):
        factor_id = factor_index[k]
        p += weight_value[weight_copy][factor[factor_id]["weightId"]] * \
            factor[factor_id]["featureValue"] * \
            eval_factor(factor_id, var_samp, value, var_copy, variable,
                        factor, fmap, var_value)
    return p


FACTORS = {  # Factor functions for boolean variables
    "FUNC_IMPLY_NATURAL": 0,
    "FUNC_OR": 1,
    "FUNC_EQUAL": 3,
    "FUNC_AND": 2,
    "FUNC_ISTRUE": 4,
    "FUNC_LINEAR": 7,
    "FUNC_RATIO": 8,
    "FUNC_LOGICAL": 9,
    "FUNC_IMPLY_MLN": 13,
             # Factor functions for categorical variables
    "FUNC_AND_CAT": 12,
    "FUNC_OR_CAT": 14,
    "FUNC_EQUAL_CAT_CONST": 15,
    "FUNC_IMPLY_NATURAL_CAT": 16,
    "FUNC_IMPLY_MLN_CAT": 17
}

for (key, value) in FACTORS.items():
    exec(key + " = " + str(value))


@jit(nopython=True, cache=True, nogil=True)
def eval_factor(factor_id, var_samp, value, var_copy, variable, factor, fmap,
                var_value):
    """TODO."""
    # Implementation of factor functions for categorical variables
    fac = factor[factor_id]
    ftv_start = fac["ftv_offset"]
    ftv_end = ftv_start + fac["arity"]

    if fac["factorFunction"] == FUNC_IMPLY_NATURAL:
        for l in range(ftv_start, ftv_end):
            v = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v == 0:
                # Early return if body is not satisfied
                return 0

        # If this point is reached, body must be true
        l = ftv_end - 1
        head = value if (fmap[l]["vid"] == var_samp) \
            else var_value[var_copy][fmap[l]["vid"]]
        if head:
            return 1
        return -1
    elif factor[factor_id]["factorFunction"] == FUNC_OR:
        for l in range(ftv_start, ftv_end):
            v = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v == 1:
                return 1
        return -1
    elif factor[factor_id]["factorFunction"] == FUNC_EQUAL:
        v = value if (fmap[ftv_start]["vid"] == var_samp) \
            else var_value[var_copy][fmap[ftv_start]["vid"]]
        for l in range(ftv_start + 1, ftv_end):
            w = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v != w:
                return -1
        return 1
    elif factor[factor_id]["factorFunction"] == FUNC_AND \
            or factor[factor_id]["factorFunction"] == FUNC_ISTRUE:
        for l in range(ftv_start, ftv_end):
            v = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v == 0:
                return -1
        return 1
    elif factor[factor_id]["factorFunction"] == FUNC_LINEAR:
        res = 0
        head = value if (fmap[ftv_end - 1]["vid"] == var_samp) \
            else var_value[var_copy][fmap[ftv_end - 1]["vid"]]
        for l in range(ftv_start, ftv_end - 1):
            v = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v == head:
                res += 1
        # This does not match Dimmwitted, but matches the eq in the paper
        return res
    elif factor[factor_id]["factorFunction"] == FUNC_RATIO:
        res = 1
        head = value if (fmap[ftv_end - 1]["vid"] == var_samp) \
            else var_value[var_copy][fmap[ftv_end - 1]["vid"]]
        for l in range(ftv_start, ftv_end - 1):
            v = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v == head:
                res += 1
        # This does not match Dimmwitted, but matches the eq in the paper
        return math.log(res)  # TODO: use log2?
    elif factor[factor_id]["factorFunction"] == FUNC_LOGICAL:
        head = value if (fmap[ftv_end - 1]["vid"] == var_samp) \
            else var_value[var_copy][fmap[ftv_end - 1]["vid"]]
        for l in range(ftv_start, ftv_end - 1):
            v = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v == head:
                return 1
        return 0
    elif factor[factor_id]["factorFunction"] == FUNC_IMPLY_MLN:
        for l in range(ftv_start, ftv_end - 1):
            v = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v == 0:
                # Early return if body is not satisfied
                return 1

        # If this point is reached, body must be true
        l = ftv_end - 1
        head = value if (fmap[l]["vid"] == var_samp) \
            else var_value[var_copy][l]
        if head:
            return 1
        return 0
    # Implementation of factor functions for categorical variables
    elif factor[factor_id]["factorFunction"] == FUNC_AND_CAT \
            or factor[factor_id]["factorFunction"] == FUNC_EQUAL_CAT_CONST:
        for l in range(ftv_start, ftv_end):
            v = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v != fmap[l]["dense_equal_to"]:
                return 0
        return 1
    elif factor[factor_id]["factorFunction"] == FUNC_OR_CAT:
        for l in range(ftv_start, ftv_end):
            v = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v == fmap[l]["dense_equal_to"]:
                return 1
        return -1
    elif factor[factor_id]["factorFunction"] == FUNC_IMPLY_NATURAL_CAT:
        for l in range(ftv_start, ftv_end - 1):
            v = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v != fmap[l]["dense_equal_to"]:
                # Early return if body is not satisfied
                return 0

        # If this point is reached, body must be true
        l = ftv_end - 1
        head = value if (fmap[l]["vid"] == var_samp) \
            else var_value[var_copy][l]
        if head == fmap[l]["dense_equal_to"]:
            return 1
        return -1
    elif factor[factor_id]["factorFunction"] == FUNC_IMPLY_MLN_CAT:
        for l in range(ftv_start, ftv_end - 1):
            v = value if (fmap[l]["vid"] == var_samp) \
                else var_value[var_copy][fmap[l]["vid"]]
            if v != fmap[l]["dense_equal_to"]:
                # Early return if body is not satisfied
                return 1

        # If this point is reached, body must be true
        l = ftv_end - 1
        head = value if (fmap[l]["vid"] == var_samp) \
            else var_value[var_copy][l]
        if head == fmap[l]["dense_equal_to"]:
            return 1
        return 0
    else:  # FUNC_UNDEFINED
        print("Error: Factor Function", factor[factor_id]["factorFunction"],
              "( used in factor", factor_id, ") is not implemented.")
        raise NotImplementedError("Factor function is not implemented.")
