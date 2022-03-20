var Socket = new WebSocket("ws://127.0.0.1:7777")
var List = document.getElementById('list')


function RemoveCurrency(Currency){
	// console.log(Currency)
	lis = List.children
	for (let i = 0; i < lis.length; i++) {
		symbol = lis[i].textContent.split(' ')[0]	//Из текста в li получаем название валютной пары
		if (symbol === Currency){
			Socket.send("DELETE "+Currency)
			List.removeChild(lis[i])
		}
	  }
}

Socket.onmessage = function (event) {
		console.log(event.data);
		let Data_object = JSON.parse(event.data)
		let li = document.createElement('li')
		str = ""
		str += Data_object.currency + " Шаг:" + Data_object.step + " Объём:" + Data_object.volume + " Докупки:" + Data_object.buy + " Продажи:" + Data_object.sell
		li.textContent = str
		input = document.createElement("input");
		input.type = "button";
		input.value = "Удалить";
		input.style = "margin-left: 10px;"
		input.symbol = Data_object.currency
		// input.onclick = RemoveCurrency(Data_object.currency);
		input.setAttribute("onclick", "RemoveCurrency(symbol)");
		li.appendChild(input);
		List.appendChild(li)
	}

var add_button = document.getElementById('add')
add_button.addEventListener('click', () => {
	currency = document.getElementById('currency').value
	volume = document.getElementById('volume').value
	step = document.getElementById('step').value
	buy = document.getElementById('buy').value
	sell =document.getElementById('sell').value
	query = new String()
	query += "NEW "+currency+' '+step+' '+volume+' '+buy+' '+sell
	Socket.send(query)
})
	
