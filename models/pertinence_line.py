# -*- coding: utf-8 -*-
from odoo import models, fields, api


CRITERES_DEFAUT = [
    {
        'critere': 'Durée du projet',
        'poids': 15.0,
        'aide': '0=<1mois | 5=3-6mois | 10=>12mois'
    },
    {
        'critere': "Chiffre d'affaires estimé",
        'poids': 20.0,
        'aide': '0=<10k€ | 5=50-100k€ | 10=>200k€'
    },
    {
        'critere': 'Cohérence savoir-faire',
        'poids': 25.0,
        'aide': '0=Hors domaine | 5=Partiel | 10=Cœur de métier'
    },
    {
        'critere': 'Potentiel futur',
        'poids': 20.0,
        'aide': '0=Ponctuel | 5=Récurrent possible | 10=Client stratégique'
    },
    {
        'critere': 'Délai de réponse',
        'poids': 10.0,
        'aide': '0=<5jours | 5=15jours | 10=>30jours'
    },
    {
        'critere': 'Localisation',
        'poids': 10.0,
        'aide': '0=Étranger | 5=Région | 10=Local'
    },
]


class CrmLeadPertinenceLine(models.Model):
    _name = 'crm.lead.pertinence.line'
    _description = 'Ligne de pertinence'
    _order = 'sequence, id'

    lead_id = fields.Many2one('crm.lead', string='Lead', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    critere = fields.Char(string='Critère', readonly=True)
    poids = fields.Float(string='Poids (%)', digits=(5, 1), readonly=True)
    aide = fields.Char(string='Guide de notation', readonly=True)
    resultat = fields.Char(string='Résultat', help="Valeur extraite par N8N (ex: 18 mois, 250 000€, Cœur de métier...)")
    note = fields.Float(string='Note (/10)', digits=(4, 1))
    total = fields.Float(string='Score', compute='_compute_total', store=True, digits=(5, 2))

    @api.depends('poids', 'note')
    def _compute_total(self):
        for rec in self:
            rec.total = (rec.poids * rec.note) / 10


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    pertinence_line_ids = fields.One2many(
        'crm.lead.pertinence.line', 'lead_id', string='Lignes de pertinence'
    )

    score_pertinence = fields.Float(
        string='Score de pertinence',
        compute='_compute_score_pertinence',
        store=True,
        digits=(5, 1),
    )

    niveau_pertinence = fields.Selection([
        ('faible', '🔴 Faible'),
        ('moyen',  '🟡 Moyen'),
        ('fort',   '🟢 Fort'),
    ], string='Niveau', compute='_compute_score_pertinence', store=True)

    @api.depends('pertinence_line_ids.total')
    def _compute_score_pertinence(self):
        for lead in self:
            score = sum(lead.pertinence_line_ids.mapped('total'))
            lead.score_pertinence = score
            if score < 40:
                lead.niveau_pertinence = 'faible'
            elif score < 70:
                lead.niveau_pertinence = 'moyen'
            else:
                lead.niveau_pertinence = 'fort'

    def _create_pertinence_lines(self):
        for seq, critere in enumerate(CRITERES_DEFAUT, start=1):
            self.env['crm.lead.pertinence.line'].create({
                'lead_id': self.id,
                'sequence': seq * 10,
                'critere': critere['critere'],
                'poids': critere['poids'],
                'aide': critere['aide'],
                'resultat': '',
                'note': 0.0,
            })

    def action_view_pertinence(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Pertinence – {self.name}',
            'res_model': 'crm.lead.pertinence.line',
            'view_mode': 'tree',
            'domain': [('lead_id', '=', self.id)],
        }

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        for lead in leads:
            lead._create_pertinence_lines()
        return leads