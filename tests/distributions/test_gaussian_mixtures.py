from __future__ import absolute_import, division, print_function

import math

import torch

import pytest
from pyro.distributions import MixtureOfDiagNormalsSharedCovariance
from tests.common import assert_equal


@pytest.mark.parametrize('mix_dist', [MixtureOfDiagNormalsSharedCovariance])
@pytest.mark.parametrize('K', [3])
@pytest.mark.parametrize('D', [3, 4])
@pytest.mark.parametrize('batch_mode', [True, False])
@pytest.mark.parametrize('flat_logits', [True, False])
@pytest.mark.parametrize('cost_function', ['quadratic'])
def test_mean_gradient(K, D, flat_logits, cost_function, mix_dist, batch_mode):
    n_samples = 1000 * 1000
    if batch_mode:
        sample_shape = torch.Size(())
    else:
        sample_shape = torch.Size((n_samples,))
    locs = torch.tensor(torch.rand(K, D), requires_grad=True)
    sigmas = torch.ones(D) + 0.5 * torch.rand(D)
    sigmas = torch.tensor(sigmas, requires_grad=True)
    if not flat_logits:
        logits = torch.tensor(1.5 * torch.rand(K), requires_grad=True)
    else:
        logits = torch.tensor(0.1 * torch.rand(K), requires_grad=True)
    omega = torch.tensor(0.2 * torch.ones(D) + 0.1 * torch.rand(D), requires_grad=False)

    _pis = torch.exp(logits)
    pis = _pis / _pis.sum()

    if cost_function == 'cosine':
        analytic1 = torch.cos((omega * locs).sum(-1))
        analytic2 = torch.exp(-0.5 * torch.pow(omega * sigmas, 2.0).sum(-1))
        analytic = (pis * analytic1 * analytic2).sum()
        analytic.backward()
    elif cost_function == 'quadratic':
        analytic = torch.pow(sigmas, 2.0).sum(-1) + torch.pow(locs, 2.0).sum(-1)
        analytic = (pis * analytic).sum()
        analytic.backward()

    analytic_grads = {}
    analytic_grads['locs'] = locs.grad.clone()
    analytic_grads['sigmas'] = sigmas.grad.clone()
    analytic_grads['logits'] = logits.grad.clone()

    sigmas.grad.zero_()
    logits.grad.zero_()
    locs.grad.zero_()

    if mix_dist == MixtureOfDiagNormalsSharedCovariance:
        params = {'locs': locs, 'sigmas': sigmas, 'logits': logits}
        if batch_mode:
            locs = locs.unsqueeze(0).expand(n_samples, K, D)
            sigmas = sigmas.unsqueeze(0).expand(n_samples, D)
            logits = logits.unsqueeze(0).expand(n_samples, K)
            dist_params = {'locs': locs, 'sigmas': sigmas, 'logits': logits}
        else:
            dist_params = params.copy()

    dist = mix_dist(*list(dist_params.values()))
    z = dist.rsample(sample_shape=sample_shape)
    if cost_function == 'cosine':
        cost = torch.cos((omega * z).sum(-1)).sum() / float(n_samples)
    elif cost_function == 'quadratic':
        cost = torch.pow(z, 2.0).sum() / float(n_samples)
    cost.backward()

    assert_equal(analytic, cost, prec=0.1,
                 msg='bad cost function evaluation for {} test (expected {}, got {})'.format(
                     mix_dist.__name__, analytic.item(), cost.item()))
    print("analytic_grads_logit", analytic_grads['logits'].detach().numpy())

    for param_name, param in params.items():
        assert_equal(param.grad, analytic_grads[param_name], prec=0.06,
                     msg='bad {} grad for {} (expected {}, got {})'.format(
                         param_name, mix_dist.__name__, analytic_grads[param_name], param.grad))


@pytest.mark.parametrize('batch_size', [1, 3])
def test_mix_of_diag_normals_shared_cov_log_prob(batch_size):
    locs = torch.tensor([[-1.0], [1.0]])
    sigmas = torch.tensor([2.0])
    logits = torch.tensor([math.log(0.25), math.log(0.75)])
    value = torch.tensor([0.5])
    if batch_size > 1:
        locs = locs.unsqueeze(0).expand(batch_size, 2, 1)
        sigmas = sigmas.unsqueeze(0).expand(batch_size, 1)
        logits = logits.unsqueeze(0).expand(batch_size, 2)
        value = value.unsqueeze(0).expand(batch_size, 1)
    dist = MixtureOfDiagNormalsSharedCovariance(locs, sigmas, logits)
    log_prob = dist.log_prob(value)
    correct_log_prob = 0.25 * math.exp(-0.5 * 2.25 / 4.0)
    correct_log_prob += 0.75 * math.exp(-0.5 * 0.25 / 4.0)
    correct_log_prob /= math.sqrt(2.0 * math.pi) * 2.0
    correct_log_prob = math.log(correct_log_prob)
    if batch_size > 1:
        correct_log_prob = [correct_log_prob] * batch_size
    correct_log_prob = torch.tensor(correct_log_prob)
    assert_equal(log_prob, correct_log_prob, msg='bad log prob for MixtureOfDiagNormalsSharedCovariance')
