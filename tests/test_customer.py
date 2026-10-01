import pytest
from src.customers.models import CustomerModel, CustomerRegistrationModel
from src.utils.helper import Helper


class TestCustomer:

    @pytest.mark.create_customer
    @pytest.mark.asyncio
    async def test_create_customer_with_valid_data(self, client):
        create_customer_payload = {
            "name": "xyz",
            "email": "prp@gmail.com",
            "address": "456, xyz street",
            "gender": "female",
            "mobile": 827272636,
            "pincode": 700135,
        }

        response = await client.post("/customers/create", json=create_customer_payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == create_customer_payload["name"]
        assert data["gender"] == create_customer_payload["gender"]
        assert data["mobile"] == create_customer_payload["mobile"]
        assert "id" in data

    @pytest.mark.invalid_customer
    @pytest.mark.asyncio
    async def test_create_customer_with_invalid_data(self, client):
        create_customer_payload = {
            "name": "",
            "email": "pradip@gmail.com",
            "address": "123, xyz street",
            "gender": "male",
            "mobile": 444444444,
            "pincode": 123456,
        }

        response = await client.post("/customers/create", json=create_customer_payload)

        assert response.status_code == 400
        data = response.json()
        print("data", data)

    @pytest.mark.login
    @pytest.mark.asyncio
    async def test_customer_login_valid(self, client, db):
        customer_register = CustomerRegistrationModel(
            id=1,
            mobile=8828162733,
            password=Helper.generate_hashed_password("asdf@1234"),
        )
        db.add(customer_register)
        await db.commit()

        customer = CustomerModel(
            id="51A30289C1",
            name="parth",
            gender="female",
            mobile=8828162733,
            email="prt@gmail.com",
            address="kolkata",
            pincode="700135",
            is_active=True,
        )
        db.add(customer)
        await db.commit()

        payload = {
            "mobile": 8828162733,
            "password": "asdf@1234",
        }

        response = await client.post("/customers/login", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
