# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PisteOffer(models.Model):
    _name = 'piste.offer'
    _description = 'Piste trouvée (projet commercial détecté)'
    _rec_name = 'name'
    _order = 'scraped_date desc'

    # =================================================================
    # CHAMPS DE BASE
    # =================================================================

    name = fields.Char(
        string="Titre du projet",
        required=True,
        help="Titre exact ou résumé du projet détecté (ex: Appel d'offres ref XYZ)"
    )

    source_id = fields.Many2one(
        'piste.source',
        string="Source de veille",
        required=True,
        ondelete='cascade',
        index=True
    )

    # =================================================================
    # INFORMATIONS DU PROJET
    # =================================================================

    url = fields.Char(
        string="Lien URL",
        help="Lien direct vers l'annonce / appel d'offres"
    )

    description = fields.Html(
        string="Description complète",
        help="Texte complet scrapé ou résumé manuel"
    )

    website = fields.Char(
        string="Plateforme / Marché",
        help="Ex: FranceTenders, BOAMP, Marchés Publics, etc."
    )

    budget = fields.Char(
        string="Budget estimé",
        help="Montant indiqué dans l'annonce (ex: 150 000 € HT)"
    )

    # =================================================================
    # STATUT ET SUIVI
    # =================================================================

    status = fields.Selection([
        ('new', 'Nouveau'),
        ('read', 'Lu / Vu'),
        ('qualified', 'Qualifié'),
        ('ignored', 'Ignoré / Non pertinent'),
        ('converted', 'Converti en piste CRM')
    ], string="Statut", default='new', required=True, tracking=True)

    publication_date = fields.Date(
        string="Date de publication",
        help="Date indiquée sur l'annonce"
    )

    scraped_date = fields.Datetime(
        string="Date de détection",
        default=fields.Datetime.now,
        required=True,
        readonly=True,
        index=True
    )

    # =================================================================
    # NOTES & LIEN VERS CRM
    # =================================================================

    notes = fields.Text(
        string="Notes commerciales",
        help="Commentaires internes, raisons du statut, etc."
    )

    lead_id = fields.Many2one(
        'crm.lead',
        string="Piste CRM créée",
        readonly=True,
        index=True,
        help="Lead généré depuis cette piste trouvée"
    )

    # =================================================================
    # MÉTHODE CONVERSION VERS PISTE (bouton dans la liste)
    # =================================================================

    def convert_to_lead(self):
        self.ensure_one()

        if self.status == 'converted':
            raise ValidationError("Cette piste a déjà été convertie en lead CRM.")

        # Préparation des valeurs pour le nouveau lead
        lead_vals = {
            'name': self.name or "Piste détectée - " + fields.Date.today().strftime('%d/%m/%Y'),
            'type': 'lead',
            'description': self.description,
            'url': self.url,  # si ton crm.lead a ce champ, sinon ajoute-le
            # Tentative de conversion budget → revenu attendu
            'expected_revenue': self._parse_budget_to_float(self.budget) or 0.0,
            # Tu peux ajouter d'autres pré-remplissages ici
            # 'Mode_de_livraison': '07 Autre',
            # 'business_unit_id': self.env.ref('ton_module.bu_par_defaut').id,
        }

        lead = self.env['crm.lead'].create(lead_vals)

        # Mise à jour de la piste
        self.write({
            'lead_id': lead.id,
            'status': 'converted',
        })

        # Notification rapide
        self.message_post(
            body=f"Piste convertie en lead CRM : <a href='#id={lead.id}&model=crm.lead'>{lead.name}</a>",
            message_type='notification'
        )

        # Ouvre le lead créé
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'view_mode': 'form',
            'res_id': lead.id,
            'target': 'current',
        }

    def _parse_budget_to_float(self, budget_str):
        """Petite fonction utilitaire pour convertir '150 000 €' → 150000.0"""
        if not budget_str:
            return 0.0
        try:
            cleaned = budget_str.replace(' ', '').replace(',', '.').replace('€', '').replace('HT', '').strip()
            return float(cleaned)
        except (ValueError, TypeError):
            return 0.0

    # =================================================================
    # CONTRAINTES
    # =================================================================

    @api.constrains('url')
    def _check_url_format(self):
        for record in self:
            if record.url and not (record.url.startswith('http://') or record.url.startswith('https://')):
                raise ValidationError("Le lien URL doit commencer par http:// ou https://")

    @api.constrains('status', 'lead_id')
    def _check_converted_consistency(self):
        for record in self:
            if record.status == 'converted' and not record.lead_id:
                raise ValidationError("Une piste au statut 'Converti en Lead' doit être liée à un lead CRM.")