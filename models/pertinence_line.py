# -*- coding: utf-8 -*-
from odoo import models, fields, api


class CrmLeadPertinenceLine(models.Model):
    _name = 'crm.lead.pertinence.line'
    _description = 'Ligne de pertinence'
    _order = 'sequence, id'

    lead_id = fields.Many2one('crm.lead', string='Lead', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    critere = fields.Char(string='Critère', readonly=True)
    poids = fields.Float(string='Poids (%)', digits=(5, 1), readonly=True)
    aide = fields.Char(string='Guide de notation', readonly=True)
    resultat = fields.Char(string='Résultat', help="Valeur extraite par N8N")
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
        """
        Crée les lignes de pertinence avec les poids depuis la veille (piste.source)
        si piste_source_id est défini, sinon utilise les valeurs par défaut.
        """
        self.ensure_one()
        
        # Mapping des critères de piste.source vers crm.lead.pertinence.line
        CRITERES_MAPPING = [
            {
                'critere': 'Savoir-faire / Adéquation métier',
                'poids_source': 'critere_savoir_poids',
                'desc_source': 'critere_savoir_desc',
                'forte_source': 'critere_savoir_forte',
                'aide_defaut': '0=Hors domaine | 5=Partiel | 10=Cœur de métier'
            },
            {
                'critere': 'Potentiel client / Récurrence',
                'poids_source': 'critere_potentiel_poids',
                'desc_source': 'critere_potentiel_desc',
                'forte_source': 'critere_potentiel_forte',
                'aide_defaut': '0=Nouveau | 5=Client occasionnel | 10=Client fidèle'
            },
            {
                'critere': "Chiffre d'affaires",
                'poids_source': 'critere_ca_poids',
                'desc_source': 'critere_ca_desc',
                'forte_source': 'critere_ca_forte',
                'aide_defaut': '0=<10k€ | 5=50-100k€ | 10=>200k€'
            },
            {
                'critere': 'Durée & récurrence du projet',
                'poids_source': 'critere_duree_poids',
                'desc_source': 'critere_duree_desc',
                'forte_source': 'critere_duree_forte',
                'aide_defaut': 'Durée: 0=<1mois | 5=3-6mois | 10=>12mois — Récurrence: 0=Ponctuel | 5=Récurrent annuel | 10=Récurrent mensuel'
            },
            {
                'critere': 'Délai de réponse',
                'poids_source': 'critere_delai_poids',
                'desc_source': 'critere_delai_desc',
                'forte_source': 'critere_delai_forte',
                'aide_defaut': '0=<5jours | 5=15jours | 10=>30jours'
            },
        ]
        
        # Si le lead a une veille associée, on prend les poids de là
        piste_source = self.piste_source_id
        
        for seq, mapping in enumerate(CRITERES_MAPPING, start=1):
            # Valeurs par défaut
            poids = 20  # Équipondération par défaut
            aide = mapping['aide_defaut']
            
            # Si veille configurée, on prend les vraies valeurs
            if piste_source:
                poids = getattr(piste_source, mapping['poids_source'], 20) or 20
                desc = getattr(piste_source, mapping['desc_source'], '') or ''
                forte = getattr(piste_source, mapping['forte_source'], '') or ''
                
                # Construit l'aide personnalisée si description ou forte existent
                if desc or forte:
                    aide_parts = []
                    if desc:
                        aide_parts.append(f"Description: {desc}")
                    if forte:
                        aide_parts.append(f"Pertinence forte si: {forte}")
                    aide = " | ".join(aide_parts)
            
            self.env['crm.lead.pertinence.line'].create({
                'lead_id': self.id,
                'sequence': seq * 10,
                'critere': mapping['critere'],
                'poids': poids,
                'aide': aide,
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