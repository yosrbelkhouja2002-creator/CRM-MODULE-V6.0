# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class PisteAPI(http.Controller):

    # =====================================================
    # 🔹 AUTHENTIFICATION VIA API KEY (ODOO 17)
    # =====================================================
    def _authenticate_api_key(self):
        auth_header = request.httprequest.headers.get('Authorization')

        if not auth_header or not auth_header.startswith('Bearer '):
            return None, request.make_response(
                json.dumps({'success': False, 'error': 'Clé API manquante'}),
                headers={'Content-Type': 'application/json'},
                status=401
            )

        key = auth_header.split(' ')[1]

        try:
            uid = request.env['res.users.apikeys']._check_credentials(
                scope='rpc',
                key=key
            )
        except Exception:
            uid = None

        if not uid:
            return None, request.make_response(
                json.dumps({'success': False, 'error': 'Clé API invalide'}),
                headers={'Content-Type': 'application/json'},
                status=401
            )

        return uid, None

    # =====================================================
    # 🔹 GET : RÉCUPÉRER LES OFFRES
    # =====================================================
    @http.route(
        '/api/piste/offer',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        save_session=False
    )
    def get_offers(self, **kw):
        
        # 🔐 Authentification
        uid, error_response = self._authenticate_api_key()
        if error_response:
            return error_response
        
        env = request.env(user=uid)
        
        try:
            # 📥 Récupérer les offres
            offers = env['piste.offer'].sudo().search([])
            
            offers_data = []
            for offer in offers:
                offers_data.append({
                    'id': offer.id,
                    'name': offer.name,
                    'url': offer.url,
                    'source_id': offer.source_id.id if offer.source_id else None,
                    'website': offer.website,
                    'description': offer.description,
                    'budget': offer.budget,
                    'publication_date': offer.publication_date.isoformat() if offer.publication_date else None,
                    'status': offer.status,
                    'scraped_date': offer.scraped_date.isoformat() if offer.scraped_date else None,
                })
            
            # ✅ Réponse
            return request.make_response(
                json.dumps({
                    'success': True,
                    'count': len(offers_data),
                    'offers': offers_data
                }),
                headers={'Content-Type': 'application/json'},
                status=200
            )
        
        except Exception as e:
            _logger.exception("Erreur get_offers")
            return request.make_response(
                json.dumps({'success': False, 'error': str(e)}),
                headers={'Content-Type': 'application/json'},
                status=500
            )

    # =====================================================
    # 🔹 POST : BULK CREATE OFFERS (n8n → Odoo)
    # =====================================================
    @http.route(
        '/api/piste/offer/bulk_create',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False
    )
    def bulk_create_offers(self, **kw):

        # 🔐 1️⃣ Authentification
        uid, error_response = self._authenticate_api_key()
        if error_response:
            return error_response

        env = request.env(user=uid)

        try:
            # 📥 2️⃣ Lire JSON
            data = json.loads(request.httprequest.data or '{}')
            offers = data.get('offers', [])

            if not offers:
                return request.make_response(
                    json.dumps({'success': False, 'error': 'Aucune offre fournie'}),
                    headers={'Content-Type': 'application/json'},
                    status=400
                )

            created_ids = []

            # 🔁 3️⃣ Création des offres
            for item in offers:

                if not item.get('url'):
                    _logger.warning(f"Offre ignorée : URL manquante - {item}")
                    continue

                source_id = item.get('source_id')
                source_name = item.get('source_name', f'Source {source_id}')
                
                # 🔹 VÉRIFIER/CRÉER LA SOURCE SI NÉCESSAIRE
                if source_id:
                    source = env['piste.source'].sudo().search([
                        ('id', '=', source_id)
                    ], limit=1)
                else:
                    source = env['piste.source'].sudo().search([
                        ('name', '=', source_name)
                    ], limit=1)
                
                if not source:
                    _logger.warning(f"Source non trouvée, création : {source_name}")
                    source = env['piste.source'].sudo().create({
                        'name': source_name,
                    })
                    source_id = source.id
                else:
                    source_id = source.id

                # Éviter doublon
                existing = env['piste.offer'].sudo().search([
                    ('url', '=', item.get('url')),
                    ('source_id', '=', source_id)
                ], limit=1)

                if existing:
                    _logger.info(f"Offre déjà existante : {item.get('url')}")
                    continue

                # ✅ Créer l'offre
                offer = env['piste.offer'].sudo().create({
                    'source_id': source_id,
                    'name': item.get('name'),
                    'url': item.get('url'),
                    'website': item.get('website'),
                    'description': item.get('description'),
                    'budget': item.get('budget'),
                    'publication_date': item.get('publication_date'),
                    'status': 'new',
                })

                created_ids.append(offer.id)
                _logger.info(f"Offre créée : ID {offer.id} - {offer.name}")

            # ✅ 4️⃣ Réponse
            return request.make_response(
                json.dumps({
                    'success': True,
                    'created_count': len(created_ids),
                    'offer_ids': created_ids
                }),
                headers={'Content-Type': 'application/json'},
                status=200
            )

        except Exception as e:
            _logger.exception("Erreur bulk_create_offers")
            return request.make_response(
                json.dumps({'success': False, 'error': str(e)}),
                headers={'Content-Type': 'application/json'},
                status=500
            )

    # =====================================================
    # 🔹 POST : CONVERTIR OFFRE → LEAD CRM
    # =====================================================
    @http.route(
        '/api/piste/offer/convert_to_lead',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False
    )
    def convert_offer_to_lead(self, **kw):

        # 🔐 Authentification
        uid, error_response = self._authenticate_api_key()
        if error_response:
            return error_response

        env = request.env(user=uid)

        try:
            # 📥 Lire JSON
            data = json.loads(request.httprequest.data or '{}')
            offer_id = data.get('offer_id')

            if not offer_id:
                return request.make_response(
                    json.dumps({'success': False, 'error': 'offer_id manquant'}),
                    headers={'Content-Type': 'application/json'},
                    status=400
                )

            # Récupérer l'offre
            offer = env['piste.offer'].sudo().browse(offer_id)
            if not offer.exists():
                return request.make_response(
                    json.dumps({'success': False, 'error': f'Offre {offer_id} non trouvée'}),
                    headers={'Content-Type': 'application/json'},
                    status=404
                )

            # Vérifier si elle est déjà convertie
            if offer.lead_id:
                return request.make_response(
                    json.dumps({
                        'success': True,
                        'lead_id': offer.lead_id.id,
                        'message': 'Offre déjà convertie'
                    }),
                    headers={'Content-Type': 'application/json'},
                    status=200
                )

            # Créer le lead CRM
            lead = env['crm.lead'].sudo().create({
                'name': offer.name,
                'description': offer.description,
                'type': 'lead',  # ou 'opportunity'
                'partner_id': offer.partner_id.id if offer.partner_id else None,
                'contact_name': offer.person_partner_id.name if offer.person_partner_id else None,
                'email_from': offer.person_partner_id.email if offer.person_partner_id else None,
                'expected_revenue': offer.budget if offer.budget else 0,
            })

            # Lier l'offre au lead
            offer.lead_id = lead.id
            offer.status = 'converted'

            return request.make_response(
                json.dumps({
                    'success': True,
                    'lead_id': lead.id,
                    'message': 'Offre convertie en Lead'
                }),
                headers={'Content-Type': 'application/json'},
                status=201
            )

        except Exception as e:
            _logger.exception("Erreur convert_offer_to_lead")
            return request.make_response(
                json.dumps({'success': False, 'error': str(e)}),
                headers={'Content-Type': 'application/json'},
                status=500
            )

    # =====================================================
    # 🔹 POST : CRÉER UNE SOURCE
    # =====================================================
    @http.route(
        '/api/piste/source/create',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False
    )
    def create_source(self, **kw):

        # 🔐 Authentification
        uid, error_response = self._authenticate_api_key()
        if error_response:
            return error_response

        env = request.env(user=uid)

        try:
            # 📥 Lire JSON
            data = json.loads(request.httprequest.data or '{}')
            name = data.get('name')

            if not name:
                return request.make_response(
                    json.dumps({'success': False, 'error': 'Nom de la source manquant'}),
                    headers={'Content-Type': 'application/json'},
                    status=400
                )

            # Vérifier si elle existe déjà
            existing = env['piste.source'].sudo().search([
                ('name', '=', name)
            ], limit=1)

            if existing:
                return request.make_response(
                    json.dumps({
                        'success': True,
                        'source_id': existing.id,
                        'message': 'Source existante'
                    }),
                    headers={'Content-Type': 'application/json'},
                    status=200
                )

            # Créer la source
            source = env['piste.source'].sudo().create({
                'name': name,
            })

            return request.make_response(
                json.dumps({
                    'success': True,
                    'source_id': source.id,
                    'message': 'Source créée'
                }),
                headers={'Content-Type': 'application/json'},
                status=201
            )

        except Exception as e:
            _logger.exception("Erreur create_source")
            return request.make_response(
                json.dumps({'success': False, 'error': str(e)}),
                headers={'Content-Type': 'application/json'},
                status=500
            )