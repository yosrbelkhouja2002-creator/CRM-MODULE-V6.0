# -*- coding: utf-8 -*-
from odoo import models, fields, api  # type: ignore
from odoo.exceptions import ValidationError  # type: ignore
import requests
import json
import logging
from datetime import datetime, timedelta
import random

_logger = logging.getLogger(__name__)


# ================================
# Modèle pour les mots-clés
# ================================
class PisteKeyword(models.Model):
    _name = 'piste.keyword'
    _description = 'Mot-clé'

    name = fields.Char(string="Mot-clé", required=True)


# ================================
# Modèle Veille commerciale
# ================================
class PisteSource(models.Model):
    _name = 'piste.source'
    _description = 'Veille commerciale'
    _rec_name = 'name'
    _order = 'name'

    # ===== IDENTIFICATION =====
    name = fields.Char(string="Nom de la veille", required=True)
    description = fields.Text(string="Description / Notes")
    active = fields.Boolean(string="Actif", default=True)

    # ===== MOTS-CLÉS =====
    keywords_required_ids = fields.Many2many(
        'piste.keyword',
        string="Mots-clés obligatoires",
        required=True
    )

    # ===== PLATEFORMES =====
    platform_marches_publics = fields.Boolean(string="Marchés Publics Gouv (Officiel)")
    platform_emarches = fields.Boolean(string="e-marchespublics.com")
    platform_francetenders = fields.Boolean(string="France Tenders")
    platform_appelaprojets = fields.Boolean(string="Appel à Projets")
    platform_marchesonline = fields.Boolean(string="Marchés Online (Payant)")
    platform_tenderimpulse = fields.Boolean(string="Tender Impulse (Payant)")
    platform_globaltenders = fields.Boolean(string="Global Tenders (Payant)")
    platform_deepbloo = fields.Boolean(string="DeepBloo (Payant)")
    platform_batieu = fields.Boolean(string="Bati EU (Payant)")
    platform_boamp = fields.Boolean(string="BOAMP (Bulletin Officiel)")
    platform_ted = fields.Boolean(string="TED - Tenders Electronic Daily (EU)")

    # ===== CRITÈRES COMMERCIAUX =====
    budget_min = fields.Integer(string="Budget minimum (€)")
    budget_max = fields.Integer(string="Budget maximum (€)")

    duration_short = fields.Boolean(string="Court terme (< 3 mois)")
    duration_medium = fields.Boolean(string="Moyen terme (3-6 mois)")
    duration_long = fields.Boolean(string="Long terme (6+ mois)")

    client_pme = fields.Boolean(string="PME / Startups")
    client_large = fields.Boolean(string="Grande entreprise")

    # ===== LOCALISATION =====
    geo_zones = fields.Many2many('res.country', string="Zones géographiques", required=True)

    # ===== UTILISATEUR QUI CRÉE =====
    creator_id = fields.Many2one(
        'res.users',
        string="Créé par",
        default=lambda self: self.env.user,
        required=True
    )

    # ===== AUTOMATISATION =====
    automation_type = fields.Selection(
        [('manual', 'Manuel'), ('auto', 'Automatique')],
        string="Type de veille",
        required=True,
        default='manual'
    )

    auto_frequency = fields.Selection([
        ('1h', 'Toutes les heures'),
        ('6h', 'Toutes les 6 heures'),
        ('12h', 'Toutes les 12 heures'),
        ('24h', 'Une fois par jour'),
        ('custom', 'Personnalisée'),
    ], string="Fréquence automatique")

    auto_date = fields.Date(string="Date de début")
    auto_time = fields.Float(string="Heure (ex: 14.30)")
    auto_repeat = fields.Selection([
        ('daily', 'Chaque jour'),
        ('2days', 'Chaque 2 jours'),
        ('weekly', 'Chaque semaine'),
        ('monthly', 'Chaque mois'),
    ], string="Répétition")

    # ===== NOTIFICATIONS =====
    notify_email = fields.Boolean(string="Notification par email", default=False)
    notify_odoo = fields.Boolean(string="Notification Odoo", default=True)
    notify_emails = fields.Text(string="Emails des destinataires")

    # ===== RELATION AVEC LES OFFRES =====
    offer_ids = fields.One2many('piste.offer', 'source_id', string='Offres trouvées')
    offer_count = fields.Integer(string="Nombre d'offres", compute='_compute_offer_count', store=True)
    last_search_date = fields.Datetime(string="Dernière recherche")

    # ===== MÉTHODES =====
    @api.depends('offer_ids')
    def _compute_offer_count(self):
        for source in self:
            source.offer_count = len(source.offer_ids)

    def action_view_offers(self):
        return {
            'type': 'ir.actions.act_window',
            'name': f'Offres - {self.name}',
            'res_model': 'piste.offer',
            'view_mode': 'tree,form',
            'domain': [('source_id', '=', self.id)],
            'context': {'default_source_id': self.id}
        }

    # ===== VALIDATION =====
    # ===== VALIDATION =====
    @api.constrains(
        'keywords_required_ids',
        'platform_marches_publics', 'platform_emarches', 'platform_francetenders',
        'platform_appelaprojets', 'platform_marchesonline', 'platform_tenderimpulse',
        'platform_globaltenders', 'platform_deepbloo', 'platform_batieu',
        'platform_boamp', 'platform_ted',
        'automation_type', 'auto_frequency', 'auto_date', 'auto_time', 'auto_repeat'
    )
    def action_run_scrape(self):
    # Sauvegarde automatique avant envoi
        self.ensure_one()
        
        n8n_webhook_url = "http://localhost:5678/webhook-test/piste-run"
        
        for source in self:
            payload = {
                'id': source.id,
                'name': source.name,
                'keywords_required': [kw.name for kw in source.keywords_required_ids],
                'platforms': {
                    'marches_publics': source.platform_marches_publics,
                    'emarches': source.platform_emarches,
                    'boamp': source.platform_boamp,
                    'francetenders': source.platform_francetenders,
                    'marchesonline': source.platform_marchesonline,
                    'globaltenders': source.platform_globaltenders,
                    'batieu': source.platform_batieu,
                    'ted': source.platform_ted,
                    'appelaprojets': source.platform_appelaprojets,
                    'tenderimpulse': source.platform_tenderimpulse,
                    'deepbloo': source.platform_deepbloo,
                },
                'budget_min': source.budget_min,
                'budget_max': source.budget_max,
                'geo_zones': [c.code for c in source.geo_zones],
                'frequency': source.auto_frequency or '',
                'auto_date': str(source.auto_date) if source.auto_date else '',
                'auto_time': source.auto_time or 0,
                'auto_repeat': source.auto_repeat or '',
                'automation_type': source.automation_type,
                'notify_email': source.notify_email,
                'notify_odoo': source.notify_odoo,
                'notify_emails': source.notify_emails or '',
                'duration_short': source.duration_short,
                'duration_medium': source.duration_medium,
                'duration_long': source.duration_long,
                'client_pme': source.client_pme,
                'client_large': source.client_large,
                'description': source.description or '',
                'creator_id': source.creator_id.id if source.creator_id else None,
            }
            
            try:
                response = requests.post(
                    n8n_webhook_url,
                    headers={'Content-Type': 'application/json'},
                    data=json.dumps(payload),
                    timeout=10
                )
                _logger.info("Scrape envoyé : %s -> %s", source.name, response.status_code)
            except Exception as e:
                _logger.error("Erreur n8n : %s", str(e))